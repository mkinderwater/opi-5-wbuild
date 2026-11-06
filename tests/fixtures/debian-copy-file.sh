# SPDX-License-Identifier: GPL-2.0-or-later
# Unmodified copy_file function from Debian initramfs-tools-core 0.148.4.
# Source: https://salsa.debian.org/kernel-team/initramfs-tools/-/blob/v0.148.4/hook-functions
# Package SHA256 recorded in tests/fixtures/README.md.
copy_file() {
	local type src target link_target

	type="${1}"
	src="${2}"
	target="${3:-$2}"

	[ -f "${src}" ] || return 2

	if [ -d "${DESTDIR}/${target}" ] || [ "${target%/}" != "$target" ]; then
		target="${target}/${src##*/}"
	fi

	# Canonicalise target to be absolute, so the comparisons below
	# will work
	target="$(realpath -ms "/${target}")" || return 2

	# Canonicalise usr-merged directories
	case "${src}" in
	/bin/* | /lib* | /sbin/*)
		[ "$(readlink -f /bin)" = /usr/bin ] && src="/usr${src}"
		;;
	esac
	case "${target}" in
	/bin/* | /lib* | /sbin/*) target="/usr${target}" ;;
	esac

	# check if already copied
	[ -e "${DESTDIR}/${target}" ] && return 1

	mkdir -p "${DESTDIR}/${target%/*}"

	# Check whether source or one of its ancestors is a symlink.
	# If so, copy the symlink target and make the target a symlink
	# too.  We don't need to replicate a chain of links completely;
	# just link directly to the ultimate target.
	link_target="$(readlink -f "${src}")" || return $(($? + 1))
	if [ "${link_target}" != "$(realpath -s "$src")" ]; then
		# Update source for the copy
		src="${link_target}"

		# Canonicalise usr-merged target directories
		case "${link_target}" in
		/bin/* | /lib* | /sbin/*) link_target="/usr${link_target}" ;;
		esac

		if [ "${link_target}" != "${target}" ]; then
			[ "${verbose?}" = "y" ] && echo "Adding ${type}-link ${target}"

			# Create a relative link so it always points
			# to the right place
			ln -rs "${DESTDIR}/${link_target}" "${DESTDIR}/${target}"
		fi

		# Copy the link target if it doesn't already exist
		target="${link_target}"
		[ -e "${DESTDIR}/${target}" ] && return 0
		mkdir -p "${DESTDIR}/${target%/*}"
	fi

	[ "${verbose}" = "y" ] && echo "Adding ${type} ${src}"

	cp -pP "${src}" "${DESTDIR}/${target}" || return $(($? + 1))
}
