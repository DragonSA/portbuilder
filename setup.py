"""Installation instructions for portbuilder"""

from distutils.core import setup

setup(name='portbuilder',
      version="0.1.2",
      description="Concurrent FreeBSD port builder.",
      author="David Naylor",
      author_email="naylor.b.david@gmail.com",
      url="http://github.com/DragonSA/portbuilder/",
      packages=["libpb", "libpb.port"],
      scripts=["portbuilder"],
      )
