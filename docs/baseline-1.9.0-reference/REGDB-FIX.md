# Regulatory database signer correction

The preceding 1.8.2 boot log showed kernel certificates sforshee and wens, followed by:

    cfg80211: loaded regulatory.db is malformed or signature is missing/invalid

Debian wireless-regdb installs two database/signature pairs. Its postinst
registers the Debian-signed pair at priority 100 and upstream-signed pair at 50.
Automatic selection therefore chose the Debian signer, benh@debian.org. Our
pinned vendor kernel trusts sforshee/wens instead. Installing files in the
initramfs alone did not establish that their signer was trusted.

The package's README.Debian specifically instructs custom upstream-kernel users
to select /lib/firmware/regulatory.db-upstream with update-alternatives. The
signature is switched through the same master group's slave link, not through
an independent selection.

The package's upstream signature was verified locally using OpenSSL against the
wens certificate extracted from the pinned kernel source. The Debian signature
did not verify with that certificate. This verifies the package and source
inputs; final acceptance on the running board still requires a reboot and log.

## Existing board

Use the repair bundle, or copy the full source directory to the board and run
scripts/fix-regdb.sh as root. It requires the known chatbox4 kernel, selects the
upstream pair, installs the corrected local initramfs hook, regenerates the
current initramfs and updates only the diagnostic files. It makes no downloads,
kernel build, SPI changes, country selection, signature-enforcement changes,
driver disabling or automatic reboot. update-initramfs can still print optional
Realtek firmware warnings; failures must not be ignored.

Reboot after successful completion, then collect:

```bash
chatbox-status --vet --compute --json > /tmp/chatbox-status-fixed.json
dmesg > /tmp/chatbox-boot-fixed.log
```

The old error remains in the current boot's dmesg until reboot. The checker does
not clear it or claim that switching a symlink retroactively fixed that boot.

## Future builds

The offline package transaction stages inputs/select-upstream-regdb.sh and runs
it after packages are configured but before final initramfs regeneration. Both
selection and signature link resolution are checked. The selection policy's
SHA-256 is recorded in build-inputs.json. The kernel/firmware/package pins and
kernel signature requirements are unchanged.

Tests use the real update-alternatives command with private admin/alternative
directories. They verify paired selection, repeat execution and failure before
mutation if the upstream signature is absent. The checker now catches the exact
reported malformed/signature message as well as missing firmware failures.

Source evidence is the pinned wireless-regdb package's README.Debian/postinst
and net/wireless/certs/wens.hex in the pinned kernel source. No new certificate
is added to the kernel and no verification policy is weakened.
