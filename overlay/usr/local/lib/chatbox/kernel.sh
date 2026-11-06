#!/bin/bash
validate_root_drivers() {
    local config=$1 listing=$2 symbol module
    while read -r symbol module; do
        if grep -qx "$symbol=y" "$config"; then
            continue
        fi
        grep -qx "$symbol=m" "$config" || { echo "Kernel lacks $symbol" >&2; return 1; }
        grep -Eq "/$module\.ko(\.(xz|zst|gz))?$" "$listing" || { echo "Initramfs lacks $module" >&2; return 1; }
    done <<'EOF'
CONFIG_BLK_DEV_NVME nvme
CONFIG_NVME_CORE nvme-core
CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY phy-rockchip-naneng-combphy
CONFIG_EXT4_FS ext4
EOF
    if grep -qx 'CONFIG_PCIE_DW_ROCKCHIP=y' "$config"; then
        return 0
    fi
    if grep -qx 'CONFIG_PCIE_ROCKCHIP_DW_HOST=y' "$config"; then
        return 0
    fi
    grep -qx 'CONFIG_PCIE_ROCKCHIP_DW_HOST=m' "$config" &&
        grep -Eq '/pcie-dw-rockchip\.ko(\.(xz|zst|gz))?$' "$listing"
}
