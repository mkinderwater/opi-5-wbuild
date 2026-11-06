"""Build a matched Rockchip kernel and pin the RKLLM runtime before image assembly."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import fdt_read


def fetch(url, path, digest, run, verify):
    # Inputs belong to one fresh build. Existing files are never reused.
    if path.exists() or path.is_symlink():
        raise ValueError('Fresh build input already exists: '+str(path))
    part=path.with_suffix(path.suffix+'.partial')
    if part.exists() or part.is_symlink():
        raise ValueError('Unexpected partial input already exists: '+str(part))
    try:
        run(['curl','--fail','--location','--proto','=https','--tlsv1.2',
             '--max-time','1200','--output',part,url])
        verify(part,digest)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return path


def check_config(text):
    # Vendor ES8323 handles the board's ES8388 compatible string. DRM_ACCEL is
    # a different ABI and is deliberately not used for Rockchip's RKLLM stack.
    required=['BLK_DEV_NVME','EXT4_FS','PCIE_DW_ROCKCHIP','PHY_ROCKCHIP_NANENG_COMBO_PHY',
              'DRM_ROCKCHIP','ROCKCHIP_VOP2','ROCKCHIP_DW_HDMI_QP',
              'DRM_FBDEV_EMULATION','FRAMEBUFFER_CONSOLE','SND_SOC_ES8323',
              'SND_SOC_ROCKCHIP_I2S_TDM','SND_SOC_ROCKCHIP_MULTICODECS',
              'ROCKCHIP_RKNPU','ROCKCHIP_RKNPU_DRM_GEM','ROCKCHIP_RKNPU_DEBUG_FS',
              'FW_LOADER',
              'DMABUF_HEAPS','DMABUF_HEAPS_SYSTEM','TRANSPARENT_HUGEPAGE',
              'TRANSPARENT_HUGEPAGE_MADVISE']
    profile=Path(__file__).resolve().parents[1]/'overlay/usr/local/lib/chatbox/container-profile.json'
    required += json.loads(profile.read_text())['required']
    if not re.search(r'^CONFIG_DRM_PANTHOR=m$',text,re.M):
        raise ValueError('Panthor must be available as a module')
    if re.search(r'^CONFIG_MALI_VALHALL=[ym]$',text,re.M):
        raise ValueError('Proprietary Valhall must not compete with Panthor')
    for key in required:
        if not re.search('^CONFIG_'+key+'=y$',text,re.M):
            raise ValueError('Vendor kernel requires CONFIG_'+key+'=y')
    if re.search(r'^CONFIG_MALI400=[ym]$', text, re.M):
        raise ValueError('Legacy Mali400 driver must not be built for the G610 board')


def apply_board_fixes(source, here):
    directory = source/'arch/arm64/boot/dts/rockchip'
    target = directory/'rk3588s-orangepi-5.dts'
    fixes = directory/'chatbox-orangepi-5-fixes.dtsi'
    include = '#include "chatbox-orangepi-5-fixes.dtsi"'
    text = target.read_text()
    if fixes.exists() or include in text:
        raise ValueError('Board fix inputs must be applied to a fresh source tree')
    fixes.write_bytes((here/'inputs/board-fixes.dtsi').read_bytes())
    target.write_text(text.rstrip()+'\n\n'+include+'\n')


def apply_mpp_metadata(source):
    path=source/'drivers/video/rockchip/mpp/Makefile'
    text=path.read_text()
    original='MPP_GIT_REVISION := \\\n'
    if text.count(original)!=1:
        raise ValueError('Unexpected MPP metadata assignment in fresh pinned source')
    # An immediate assignment still expands its shell expression even when a
    # command-line variable overrides it. Conditional assignment avoids Git.
    path.write_text(text.replace(original,'MPP_GIT_REVISION ?= \\\n',1))


def check_tree(path):
    root=fdt_read.parse(path)
    if b'rockchip,rk3588s-orangepi-5\0' not in root.props.get('compatible',b''):
        raise ValueError('Vendor DTB is not original Orange Pi 5')
    nodes={}
    def walk(n,p=''):
        p=p+'/'+n.name
        nodes[p]=n
        for c in n.children:walk(c,p.rstrip('/'))
    walk(root)
    for p in ['/vop@fdd90000','/hdmi@fde80000','/es8388-sound',
              '/i2c@fec80000','/i2c@fec80000/es8388@10','/i2s@fe480000',
              '/npu@fdab0000','/iommu@fdab9000','/gpu-panthor@fb000000']:
        n=nodes.get(p)
        if n is None or n.props.get('status',b'okay\0').rstrip(b'\0') not in (b'okay',b'ok'):
            raise ValueError('Vendor DTB missing/disabled '+p)
    if b'arm,mali-valhall-csf\0' not in nodes['/gpu-panthor@fb000000'].props.get('compatible',b''):
        raise ValueError('GPU DTB does not match Panthor')
    competing=nodes.get('/gpu@fb000000')
    if competing and competing.props.get('status',b'okay\0').rstrip(b'\0') != b'disabled':
        raise ValueError('Proprietary GPU DT node must be disabled')
    gpu=nodes['/gpu-panthor@fb000000']
    supply=gpu.props.get('mali-supply')
    regulator=next((node for node in nodes.values() if supply and node.props.get('phandle')==supply),None)
    if regulator is None or regulator.props.get('status',b'okay\0').rstrip(b'\0') not in (b'okay',b'ok'):
        raise ValueError('Panthor GPU regulator is missing or disabled')
    if b'everest,es8323\0' not in nodes['/i2c@fec80000/es8388@10'].props.get('compatible',b''):
        raise ValueError('Audio codec does not match vendor driver')
    if b'rockchip,rk3588-rknpu\0' not in nodes['/npu@fdab0000'].props.get('compatible',b''):
        raise ValueError('NPU DTB does not match vendor ABI')
    check_board_fixes(nodes)
    for parent,prop,child in [('/es8388-sound','rockchip,codec','/i2c@fec80000/es8388@10'),
                               ('/es8388-sound','rockchip,cpu','/i2s@fe480000'),
                               ('/npu@fdab0000','iommus','/iommu@fdab9000')]:
        target=nodes[child].props.get('phandle')
        if not target or nodes[parent].props.get(prop,b'')[:4]!=target:
            raise ValueError('Vendor DTB has unmatched '+prop)


def check_board_fixes(nodes):
    led = nodes.get('/gpio-leds/led@1')
    group = nodes.get('/pinctrl/gpio-func/leds-gpio')
    gpio = nodes.get('/pinctrl/gpio@fec20000')
    controller = nodes.get('/gpio-leds')
    if not all((led, group, gpio, controller)):
        raise ValueError('Missing LED pin mapping')
    if (len(group.props.get('rockchip,pins', b'')) != 16
            or group.props.get('rockchip,pins', b'')[:12] != struct.pack('>III', 1, 2, 0)
            or not gpio.props.get('phandle')
            or led.props.get('gpios', b'') != gpio.props['phandle'] + struct.pack('>II', 2, 0)
            or not group.props.get('phandle')
            or controller.props.get('pinctrl-0') != group.props['phandle']):
        raise ValueError('LED GPIO and pinctrl must both select GPIO1_A2')
    gpu=nodes.get('/gpu-panthor@fb000000')
    cooling=nodes.get('/thermal-zones/soc-thermal/cooling-maps/map3')
    if not gpu or not cooling or not gpu.props.get('phandle') or cooling.props.get('cooling-device',b'')[:4] != gpu.props['phandle']:
        raise ValueError('Thermal map must reference the active Panthor GPU')



def stream(args):
    result=subprocess.run([str(x) for x in args])
    if result.returncode:
        raise RuntimeError('Kernel build failed; see compiler output above')


def package(tree, destination, name, version, depends, postinst, run):
    control=tree/'DEBIAN';control.mkdir(parents=True)
    (control/'control').write_text(f'Package: {name}\nVersion: {version}\nArchitecture: arm64\nMaintainer: Chatbox local builder <root@localhost>\nDepends: {depends}\nDescription: Chatbox pinned Orange Pi 5 hardware support\n')
    (control/'postinst').write_text('#!/bin/sh\nset -eu\n'+postinst+'\n')
    (control/'postinst').chmod(0o755)
    run(['dpkg-deb','--root-owner-group','-Zgzip','--build',tree,destination])
    return {'Package':name,'Version':version,'Architecture':'arm64',
            'Filename':destination.name,'SHA256':hashlib.sha256(destination.read_bytes()).hexdigest()}


def package_kernel(source,obj,work,downloads,abi,version,run,make,here):
    lock=json.loads((here/'inputs/hardware-lock.json').read_text())
    dtb=obj/'arch/arm64/boot/dts/rockchip/rk3588s-orangepi-5.dtb'
    tree=work/'package'
    boot=tree/'boot';boot.mkdir(parents=True)
    for src,dst in [(obj/'arch/arm64/boot/Image',boot/('vmlinuz-'+abi)),
                    (obj/'.config',boot/('config-'+abi)),(obj/'System.map',boot/('System.map-'+abi))]:
        shutil.copyfile(src,dst)
    dtbdir=tree/('usr/lib/linux-image-'+abi)/'rockchip';dtbdir.mkdir(parents=True)
    shutil.copyfile(dtb,dtbdir/dtb.name)
    stream([*make,'INSTALL_MOD_PATH='+str(tree.resolve()),'INSTALL_MOD_STRIP=1','modules_install'])
    if not any(p.name=='panthor.ko' for p in (tree/'lib/modules'/abi).rglob('*.ko')):
        raise ValueError('Panthor module missing from kernel package')
    for name in ['build','source']:
        (tree/'lib/modules'/abi/name).unlink(missing_ok=True)
    package_name='linux-image-'+abi
    doc=tree/'usr/share/doc'/package_name;doc.mkdir(parents=True)
    shutil.copyfile(source/'COPYING',doc/'copyright')
    shutil.copyfile(source/'LICENSES/preferred/GPL-2.0',doc/'GPL-2.0')
    shutil.copyfile(here/'inputs/kernel.fragment',doc/'kernel.fragment')
    shutil.copyfile(here/'overlay/usr/local/lib/chatbox/container-profile.json',doc/'container-profile.json')
    shutil.copyfile(here/'inputs/board-fixes.dtsi',doc/'board-fixes.dtsi')
    (doc/'source.json').write_text(json.dumps(lock['kernel'],indent=2)+'\n')
    hook=tree/'etc/initramfs-tools/hooks/chatbox-regdb'
    hook.parent.mkdir(parents=True)
    shutil.copyfile(here/'inputs/initramfs-regdb-hook',hook)
    hook.chmod(0o755)
    kernel_path=downloads/(package_name+'_'+version+'_arm64.deb')
    meta=package(tree,kernel_path,package_name,version,'kmod, initramfs-tools',
                 f'if [ "$1" = configure ]; then\n depmod {abi}\n if [ -s /boot/initrd.img-{abi} ]; then\n  update-initramfs -u -k {abi}\n else\n  update-initramfs -c -k {abi}\n fi\nfi',run)
    return meta,kernel_path


def prepare(here, downloads, run, verify):
    lock=json.loads((here/'inputs/hardware-lock.json').read_text())
    if downloads.exists():
        raise ValueError('Build download directory must be fresh: '+str(downloads))
    downloads.mkdir(parents=True)
    abi=lock['kernel_abi'];version=lock['version']
    tools={'compiler':run(['aarch64-linux-gnu-gcc','--version']).splitlines()[0],
           'linker':run(['aarch64-linux-gnu-ld','--version']).splitlines()[0]}
    for name,value in tools.items():print(name+': '+value,flush=True)
    archive=fetch(lock['kernel']['url'],downloads/'kernel-source.tar.gz',lock['kernel']['SHA256'],run,verify)
    # Rebuild from pinned source and the current fragment. Never trust a stale
    # locally generated kernel package solely because its filename matches.
    with tempfile.TemporaryDirectory(prefix='kernel-build-',dir=downloads) as d:
        work=Path(d)
        with tarfile.open(archive) as tar:
            # Source contains internal symlinks. Python's data filter confines
            # extraction, rejecting external paths and special files.
            tar.extractall(work,filter='data')
        source=work/('linux-rockchip-'+lock['kernel']['commit'])
        apply_board_fixes(source, here)
        apply_mpp_metadata(source)
        mpp_makefile_sha256=hashlib.sha256((source/'drivers/video/rockchip/mpp/Makefile').read_bytes()).hexdigest()
        obj=work/'obj';obj.mkdir()
        mpp_revision='chatbox-pinned-'+lock['kernel']['commit']
        make=['make','-C',source,'O='+str(obj.resolve()),'ARCH=arm64','CROSS_COMPILE=aarch64-linux-gnu-',
              'MPP_GIT_REVISION='+mpp_revision]
        stream([*make,'rockchip_linux_defconfig'])
        # merge_config without its implicit make, so our ARCH/O always apply.
        stream(['bash',source/'scripts/kconfig/merge_config.sh','-m','-O',obj,obj/'.config',here/'inputs/kernel.fragment'])
        stream([*make,'olddefconfig'])
        # kernelrelease reads include/config/auto.conf, not .config.
        stream([*make,'syncconfig'])
        check_config((obj/'.config').read_text())
        actual=run([*make,'-s','kernelrelease']).strip().splitlines()
        if abi not in actual:
            raise ValueError('Built kernel ABI differs from hardware lock: '+repr(actual))
        header=(source/'drivers/rknpu/include/rknpu_drv.h').read_text()
        for key,value in [('MAJOR',0),('MINOR',9),('PATCHLEVEL',8)]:
            if not re.search(r'^#define DRIVER_'+key+r'\s+'+str(value)+r'$',header,re.M):
                raise ValueError('Pinned RKNPU driver is not 0.9.8')
        jobs=os.environ.get('CHATBOX_JOBS',str(min(os.cpu_count() or 2,2)))
        if not re.fullmatch(r'[1-9][0-9]*',jobs):raise ValueError('Invalid CHATBOX_JOBS')
        stream([*make,'-j'+jobs,'Image','modules','rockchip/rk3588s-orangepi-5.dtb'])
        dtb=obj/'arch/arm64/boot/dts/rockchip/rk3588s-orangepi-5.dtb'
        check_tree(dtb)
        meta,kernel_path=package_kernel(source,obj,work,downloads,abi,version,run,make,here)
    # Keep every installed package in one verified staging directory for the read-only bind.
    all_meta=[meta];paths=[kernel_path]
    for item in lock['packages']:
        path=fetch('https://deb.debian.org/debian/'+item['Filename'],downloads/Path(item['Filename']).name,item['SHA256'],run,verify)
        for field in ['Package','Version','Architecture']:
            if run(['dpkg-deb','-f',path,field]).strip()!=item[field]:
                raise ValueError('Package metadata mismatch: '+path.name)
        all_meta.append(item);paths.append(path)
    runtime=lock['rkllm']
    for item in runtime['files']:
        fetch(item['url'],downloads/item['name'],item['SHA256'],run,verify)
    elf=(downloads/'librkllmrt.so').read_bytes()
    if elf[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(elf[18:20],'little')!=183:
        raise ValueError('RKLLM runtime is not an ARM64 ELF library')
    with tempfile.TemporaryDirectory(prefix='runtime-build-',dir=downloads) as d:
        tree=Path(d)/'package';lib=tree/'usr/lib/aarch64-linux-gnu';lib.mkdir(parents=True)
        shutil.copyfile(downloads/'librkllmrt.so',lib/'librkllmrt.so')
        doc=tree/'usr/share/doc/chatbox-rkllm-runtime';doc.mkdir(parents=True)
        shutil.copyfile(downloads/'LICENSE',doc/'copyright')
        (doc/'source.json').write_text(json.dumps(runtime,indent=2)+'\n')
        path=downloads/('chatbox-rkllm-runtime_'+runtime['version']+'-1_arm64.deb')
        all_meta.append(package(tree,path,'chatbox-rkllm-runtime',runtime['version']+'-1',
                                'libc6 (>= 2.38), libstdc++6, libgcc-s1, libgomp1',
                                'if [ "$1" = configure ]; then ldconfig; fi',run))
        paths.append(path)
    gpu_meta,gpu_path=package_opencl(here,downloads,lock,paths,run,verify)
    all_meta.append(gpu_meta);paths.append(gpu_path)
    result={**lock,'packages':all_meta,'build_tools':tools,'mpp_revision_label':mpp_revision,
            'mpp_makefile_sha256':mpp_makefile_sha256,
            'container_profile_sha256':hashlib.sha256((here/'overlay/usr/local/lib/chatbox/container-profile.json').read_bytes()).hexdigest(),
            'fragment_sha256':hashlib.sha256((here/'inputs/kernel.fragment').read_bytes()).hexdigest(),
            'initramfs_regdb_hook_sha256':hashlib.sha256((here/'inputs/initramfs-regdb-hook').read_bytes()).hexdigest(),
            'regdb_selection_sha256':hashlib.sha256((here/'inputs/select-upstream-regdb.sh').read_bytes()).hexdigest(),
            'board_fixes_sha256':hashlib.sha256((here/'inputs/board-fixes.dtsi').read_bytes()).hexdigest()}
    return result,paths



def package_opencl(here,downloads,lock,paths,run,verify):
    """Package API-independent numeric check; Mesa and firmware come from pinned debs."""
    with tempfile.TemporaryDirectory(prefix='opencl-build-',dir=downloads) as d:
        work=Path(d);dependencies=work/'dependencies'
        for item,path in zip(lock['packages'],paths[1:]):
            if item['Package'] in ('ocl-icd-libopencl1','opencl-c-headers','libvulkan1','libvulkan-dev'):
                run(['dpkg-deb','-x',path,dependencies])
        tree=work/'package'
        doc=tree/'usr/share/doc/chatbox-gpu-tools';doc.mkdir(parents=True)
        (doc/'source.json').write_text(json.dumps(lock['gpu'],indent=2)+'\n')
        program=tree/'usr/local/sbin/chatbox-opencl-check';program.parent.mkdir(parents=True)
        run(['aarch64-linux-gnu-gcc','-O2','-Wall','-Wextra','-Werror',
             '-I'+str(dependencies/'usr/include'),here/'scripts/opencl-check.c',
             '-L'+str(dependencies/'usr/lib/aarch64-linux-gnu'),'-Wl,--no-as-needed',
             '-l:libOpenCL.so.1','-o',program])
        program.chmod(0o755)
        shader=work/'gpu.spv'
        run(['glslangValidator','-V','--target-env','vulkan1.0',here/'scripts/gpu-shader.comp','-o',shader])
        data=shader.read_bytes()
        if len(data)%4 or data[:4]!=b'\x03\x02\x23\x07':
            raise ValueError('Invalid compiled SPIR-V')
        words=struct.unpack('<'+'I'*(len(data)//4),data)
        (work/'gpu-shader.h').write_text('static const uint32_t shader_words[] = {'+','.join(hex(w) for w in words)+'};\n')
        vkprogram=program.with_name('chatbox-vulkan-check')
        run(['aarch64-linux-gnu-gcc','-O2','-Wall','-Wextra','-Werror',
             '-I'+str(dependencies/'usr/include'),'-I'+str(work),here/'scripts/vulkan-check.c',
             '-L'+str(dependencies/'usr/lib/aarch64-linux-gnu'),'-Wl,--allow-shlib-undefined','-l:libvulkan.so.1','-o',vkprogram])
        vkprogram.chmod(0o755)
        path=downloads/'chatbox-gpu-tools_2.0.1-1_arm64.deb'
        meta=package(tree,path,'chatbox-gpu-tools','2.0.1-1',
                     'libc6 (>= 2.38), ocl-icd-libopencl1, mesa-opencl-icd, mesa-vulkan-drivers, clinfo, vulkan-tools',
                     'if [ "$1" = configure ]; then ldconfig; fi',run)
    return meta,path
