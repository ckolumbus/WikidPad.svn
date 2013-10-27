'''Select the best kjbuckets module available.

:Author: Richard Jones
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: kjbuckets_select.py,v 1.1 2006/01/07 15:01:24 Michael Butscher Exp $:
'''

# use kjbuckets builtin if available
try:
    import kjbuckets
except ImportError:
    import kjbuckets0
    kjbuckets = kjbuckets0

#
# $Log: kjbuckets_select.py,v $
# Revision 1.1  2006/01/07 15:01:24  Michael Butscher
# First combined version of WikidPad/WikidPadCompact
#
# Revision 1.1  2005/06/05 05:51:23  jhorman
# initial checkin
#
# Revision 1.3  2002/05/11 02:59:05  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
#
