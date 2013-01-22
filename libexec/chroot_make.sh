#!/bin/sh

set -e

MASTER_CHROOT="/scratchpad/9.1_pkg_env_amd64"
WORLDSRC="/home/freebsd/9.1/world-amd64.tar.xz"

# Check argument
if [ $# -ne 1 ]
then
	echo "usage: $0 <chroot>"
	exit 1
fi
CHROOT=$1

# Check for clean chroot
if [ -d $CHROOT ]
then
	echo "err: $CHROOT already exists"
	exit 1
fi

# Initialise chroot
mkdir -p $CHROOT
if [ -n "$TINDERBOX_SLOW" ]
then
	tar -C $CHROOT -xf $WORLDSRC
else
	# Uncomment the following to stress test tmpfs (WARNING: may crash system)
	#mount -t tmpfs tmp $CHROOT
	mount -t unionfs -o below,noatime $MASTER_CHROOT $CHROOT
fi
mount | grep nullfs | while read line
do
	mounton=`echo $line | cut -f 3 -d ' '`
	if [ -n "`echo $mounton | grep ^$MASTER_CHROOT`" ]
	then
		mountfrom=`echo $line | cut -f 1 -d ' '`
		if [ -n "`echo $line | grep readonly`" ]
		then
			ro="-o ro"
		else
			ro=""
		fi
		mounton=`echo $mounton | sed "s|$MASTER_CHROOT/||"`
		mkdir -p $CHROOT/$mounton
		mount -t nullfs -o noatime $ro $mountfrom $CHROOT/$mounton
		# HACK: workaround for kern/175449
		touch $CHROOT/$mounton
	fi
done
mkdir -p $MASTER_CHROOT/usr/ports/packages $CHROOT/usr/ports/packages
mount -t nullfs -o noatime $MASTER_CHROOT/usr/ports/packages $CHROOT/usr/ports/packages
# HACK: workaround for kern/175449
touch $CHROOT/usr/ports/packages
for dir in dev proc tmp
do
	mkdir -p $CHROOT/$dir
	mount -t ${dir}fs $MASTER_CHROOT/$dir $CHROOT/$dir
done
# HACK: workaround for kern/175449
touch $CHROOT/dev
mkdir -p $CHROOT/compat/linux/proc
mount -t linprocfs linprocfs $CHROOT/compat/linux/proc
