# New ports collection Makefile for:	portbuilder
# Date created:				2011/04/03
# Whom:					David Naylor <naylor.b.david@gmail.com>
#
# $FreeBSD: ports/ports-mgmt/portbuilder/Makefile,v 1.3 2011/07/25 01:40:44 zi Exp $

PORTNAME=	portbuilder
DISTVERSION=	0.1.3.1
PORTREVISION=	1
CATEGORIES=	ports-mgmt
MASTER_SITES=	http://cloud.github.com/downloads/DragonSA/portbuilder/

MAINTAINER=	naylor.b.david@gmail.com
COMMENT=	Concurrent FreeBSD port builder

LICENSES=	BSD

USE_PYTHON=	2.6+
USE_PYDISTUTILS=yes
USE_XZ=		yes

PORTDOCS=	BUGS ChangeLog COPYRIGHT README

post-install:
.if !defined(NOPORTDOCS)
	${MKDIR} ${DOCSDIR}
.for file in ${PORTDOCS}
	${INSTALL_DATA} ${WRKSRC}/${file} ${DOCSDIR}
.endfor
.endif

.include <bsd.port.mk>
