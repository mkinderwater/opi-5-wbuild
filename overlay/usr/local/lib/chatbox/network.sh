#!/bin/bash
# Accept networkctl's complete Address block, including IPv6-first layouts.
parse_ipv4() {
    awk '
    function ipv4(s, a,n,i) {
        sub(/\/[0-9]+$/, "", s)
        if (s !~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) return ""
        n=split(s,a,".")
        for(i=1;i<=n;i++) if(a[i]>255) return ""
        if(a[1]==0 || a[1]==127 || (a[1]==169 && a[2]==254)) return ""
        return s
    }
    /Address:/ { active=1; sub(/^.*Address:[[:space:]]*/, "") }
    active && /^[[:space:]]*[[:alpha:]][[:alnum:] _-]*:[[:space:]]/ {active=0}
    active {for(i=1;i<=NF;i++) {s=ipv4($i); if(s!="") {print s; exit}}}
    '
}

ethernet_address() {
    local path interface address
    for path in /sys/class/net/*; do
        if [ ! -d "$path/device" ] || [ -d "$path/wireless" ]; then continue; fi
        [ "$(cat "$path/type")" = 1 ] || continue
        interface=${path##*/}
        address=$(SYSTEMD_COLORS=0 networkctl status "$interface" --no-pager 2>/dev/null | parse_ipv4) || true
        if [ -n "$address" ]; then printf '%s %s\n' "$interface" "$address"; return 0; fi
    done
    return 1
}
