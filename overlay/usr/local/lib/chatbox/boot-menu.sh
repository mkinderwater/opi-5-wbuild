#!/bin/bash
render_boot_menu() {
    local choice=$1 abi=$2 root_id=$3
    [[ "$choice" = display || "$choice" = recovery ]] || return 1
    [[ "$abi" =~ ^[0-9A-Za-z.+_-]+$ ]] || return 1
    [[ "$root_id" =~ ^[0-9a-f]{8}-02$ ]] || return 1
    cat <<EOF
DEFAULT $choice
TIMEOUT 50
MENU TITLE Chatbox boot
LABEL display
  MENU LABEL Chatbox hardware kernel
  LINUX /boot/vmlinuz-$abi
  INITRD /boot/initrd.img-$abi
  FDT /boot/chatbox-orangepi-5.dtb
  APPEND root=PARTUUID=$root_id rw rootwait console=ttyFIQ0,1500000n8 console=tty1 loglevel=6 systemd.show_status=yes
LABEL recovery
  MENU LABEL Chatbox recovery kernel
  LINUX /boot/vmlinuz-6.12.113+deb13-arm64
  INITRD /boot/initrd.img-6.12.113+deb13-arm64
  FDT /boot/chatbox-recovery.dtb
  APPEND root=PARTUUID=$root_id rw rootwait console=ttyS2,1500000n8 console=tty1 loglevel=6 systemd.show_status=yes
EOF
}
