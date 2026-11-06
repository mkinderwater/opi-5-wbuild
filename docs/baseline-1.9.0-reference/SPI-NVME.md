# SPI and NVMe bring-up

The RK3588S BootROM does not directly load this NVMe image. The board needs
boot firmware in SPI that initializes the board, enumerates its NVMe and loads
our extlinux entry from the ext4 root partition.

The supplied Johang boot image is a 32 MiB **disk boot prefix**, not a confirmed
SPI-flash payload. Inspection found:

- MBR partition 1 type 0x0c: LBA 8192, length 57344 sectors.
- MBR partition 2 type 0x83: LBA 65536, length 7354368 sectors.
- Rockchip loader data at offset 32768.
- FIT header at offset 8388608, inside the nominal partition-1 range.
- The nominal FAT partition does not contain a valid FAT32 boot sector.
- U-Boot identifies the original Orange Pi 5 and includes NVMe in boot_targets.

Therefore formatting the source's apparent FAT partition would corrupt its
bootloader. Our NVMe image has a fresh layout and contains no raw bootloader.

A `u-boot-rockchip-spi.bin` string inside U-Boot is not proof of a separately
extractable, validated SPI image. Do not write the complete 32 MiB input to SPI,
and do not extract arbitrary offsets as a flash payload.

## Safe bring-up order

1. Identify the board revision and existing SPI firmware. Record the board's
   serial-console boot log. If replacing SPI, preserve a readable dump first.
2. Establish an appropriate Orange Pi 5 SPI-format firmware from a documented
   source and verify that exact image's flash layout and board compatibility.
   This remains unfinished work; this release has no SPI writer.
3. With working SPI U-Boot, verify NVMe enumeration and ext4 access. Typical
   read-only commands, if present in that U-Boot build:

   ```text
   version
   printenv boot_targets fdtfile
   nvme scan
   nvme info
   part list nvme 0
   ls nvme 0:2 /boot
   ls nvme 0:2 /boot/extlinux
   ```

4. Boot the NVMe and verify the kernel sees its NVMe root by PARTUUID.
5. Remove temporary SD/USB boot media and cold boot repeatedly.

A successful offline image build is not evidence of successful SPI programming
or a board boot. Never run SPI erase/write commands based on this document.
