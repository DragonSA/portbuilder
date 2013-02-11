#!/bin/sh

set -e

MASTER_CHROOT="/scratchpad/9.1_pkg_env_amd64"

# Check argument
if [ $# -ne 1 ]
then
	echo "usage: $0 <chroot>"
	exit 1
fi
CHROOT=`realpath $1`

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
