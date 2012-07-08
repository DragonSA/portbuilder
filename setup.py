"""Installation instructions for portbuilder"""

from distutils.core import setup

long_description="""
A concurrent ports building tool.  Although FreeBSD ports supports building a
single port using multiple jobs (via MAKE_JOBS) however it cannot build
multiple ports concurrently.  This tool accomplishes just that.

Some of its key features:
 * Concurrent port building
 * Load control
 * Top like UI
 * Persistent builds (by default)

WWW: http://github.com/DragonSA/portbuilder/
"""

setup(name='portbuilder',
      version="0.1.5.2",
      description="Concurrent FreeBSD port builder",
      long_description=long_description,
      author="David Naylor",
      author_email="naylor.b.david@gmail.com",
      url="http://github.com/DragonSA/portbuilder/",
      download_url="http://cloud.github.com/downloads/DragonSA/portbuilder/portbuilder-0.1.5.2.tar.xz",
      packages=["libpb", "libpb/port", "libpb/pkg", "libpb/stacks",],
      scripts=["portbuilder",],
      classifiers=[
            "Development Status :: 3 - Alpha",
            "Environment :: Console",
            "Environment :: Console :: Curses",
            "License :: OSI Approved :: BSD License",
            "Natural Language :: English",
            "Operating System :: POSIX :: BSD :: FreeBSD",
            "Programming Language :: Python",
            "Programming Language :: Python :: 2.6",
            "Programming Language :: Python :: 2.7",
            ]
      )
