#!/bin/sh

set -e

abs_path() {

	local cwd
	local path
	cwd=$1
	path=$2

	if [ -n "`echo $path |  cut -f 1 -d '/'`" ]
	then
		echo $cwd/$path
	else
		echo $path
	fi

}

readlink_R() {

	local path
	local link
	local newpath
	path=`abs_path $PWD $1`
	
	set +e

	link=`readlink $path`
	while [ -n "$link" ]
	do
		path=`abs_path $(dirname $path) $link`
		link=`readlink $path`
	done

	newpath="/"
	for part in `echo $path | sed 's|/| |g'`
	do
		case $part in
			.) ;;
			..) newpath=`dirname $newpath` ;;
			*) 
			if [ $newpath = / ]
			then
				newpath=/$part
			else
				newpath=$newpath/$part
			fi ;;
		esac
	done
	
	echo $newpath

}

MASTER_CHROOT="/scratchpad/9.1_pkg_env_amd64"

# Check argument
if [ $# -ne 1 ]
then
	echo "usage: $0 <chroot>"
	exit 1
fi
CHROOT=`readlink_R $1`

# Check for existing chroot
if [ ! -d $CHROOT ]
then
	echo "err: $CHROOT does not exist"
	exit 1
fi

# Initialise chroot
mount | cut -f 3 -d ' ' | grep ^$CHROOT | sort -r | while read mounton
do
	umount -f $mounton
done
if [ -n "$TINDERBOX_SLOW" ]
then
	rm -rf $CHROOT || (chflags -R 0 $CHROOT; rm -rf $CHROOT)
else
	rm -rf $CHROOT
fi
