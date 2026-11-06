#!/bin/sh
# Debian's upstream-signed alternative matches this pinned vendor kernel's keys.
set -eu
for name in regulatory.db-upstream regulatory.db.p7s-upstream; do
    [ -s "/usr/lib/firmware/$name" ] || {
        echo "E: required upstream regulatory firmware missing: $name" >&2; exit 1;
    }
done
# This master alternative also selects regulatory.db.p7s through its slave link.
update-alternatives --set regulatory.db /lib/firmware/regulatory.db-upstream
for name in regulatory.db regulatory.db.p7s; do
    selected=$(readlink -f "/usr/lib/firmware/$name")
    expected=$(readlink -f "/usr/lib/firmware/$name-upstream")
    [ "$selected" = "$expected" ] || {
        echo "E: upstream regulatory database/signature selection mismatch" >&2; exit 1;
    }
done
