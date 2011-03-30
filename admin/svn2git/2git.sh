#!/bin/sh
# svn2git comes from: http://gitorious.org/svn2git/svn2git (devel/svn2git)

REPO=${REPO:-/home/DragonSA/archive/projects/pypkg/}

cd `dirname $0`

svn2git --identity-map=authors.txt --rules=rules.txt --stats ${REPO}

(cd portbuilder;
	git config core.bare false;
	mkdir .git;
	mv * .git/;
	git checkout --;)
