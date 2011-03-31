#!/bin/sh
# svn2git comes from: http://gitorious.org/svn2git/svn2git (devel/svn2git)

REPO=${REPO:-/home/DragonSA/archive/projects/pypkg/}

BASE=`dirname $0`

# Convert to git
if svn2git --identity-map=$BASE/authors.txt --rules=$BASE/rules.txt --stats ${REPO}
then
	rm log-portbuilder
else
	exit 1
fi

(cd portbuilder;
	git filter-branch --tag-name-filter cat --msg-filter "sed -E '/^ r[0-9]+@.*:  .* | [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} \+[0-9]{4}$/D'" -- --all;
	git filter-branch --tag-name-filter cat --msg-filter 'tee `mktemp /tmp/log.XXXXX`';
	git for-each-ref --format='%(refname)' refs/original/ refs/remotes/svn/ | while read ref;
	do
		git update-ref -d "$ref";
	done;
	git reflog expire --all --expire=now;
	git gc --aggressive;
	git prune;
	git fsck --full)

# Make bare git repository a normal git repository
# To skip uncomment next line
# exit 0
(cd portbuilder;
	git config core.bare false;
	mkdir .git;
	mv * .git/;
	git checkout --;)
