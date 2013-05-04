## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

# Official parser plugin for MediaWiki language "MediaWiki 1"
# Last modified (format YYYY-MM-DD): 2013-04-29


import locale, pprint, time, sys, string, traceback

from textwrap import fill

import wx

import re    # from pwiki.rtlibRepl import re
from pwiki.WikiExceptions import *
from pwiki.StringOps import revStr, urlFromPathname, \
        urlQuoteSpecific, HtmlStartTag, HtmlEmptyTag, HtmlEndTag

from pwiki.WikiDocument import WikiDocument
from pwiki.OptionsDialog import PluginOptionsPanel

sys.stderr = sys.stdout

locale.setlocale(locale.LC_ALL, '')

from pwiki.WikiPyparsing import *


WIKIDPAD_PLUGIN = (("WikiParser", 1),)

WIKI_LANGUAGE_NAME = "mediawiki_1"
WIKI_HR_LANGUAGE_NAME = u"MediaWiki 1.0"





# The specialized optimizer in WikiPyParsing can't handle automatic whitespace
# removing
ParserElement.setDefaultWhitespaceChars("")



RE_FLAGS = re.DOTALL | re.UNICODE | re.MULTILINE


def buildRegex(regex, name=None, hideOnEmpty=False):
    if name is None:
        element = Regex(regex, RE_FLAGS)
    else:
        element = Regex(regex, RE_FLAGS).setResultsName(name).setName(name)
    
    if hideOnEmpty:
        element.setParseAction(actionHideOnEmpty)
        
    return element

stringEnd = buildRegex(ur"(?!.)", "stringEnd")



def getFirstTerminalNode(t):
    if t.getChildrenCount() == 0:
        return None
    
    lt = t[-1]
    if not isinstance(lt, TerminalNode):
        return None
        
    return lt


def actionHideOnEmpty(s, l, st, t):
    if t.strLength == 0:
        return []


def actionSetHelperNodeRecur(s, l, st, t):
    """
    Set as helper node which is recursively processed by editor and renderers
    even if it is unknown
    """
    if t.name != None:
        t.helperNode = True
        t.helperRecursive = True
    else:
        t[0].helperNode = True
        t[0].helperRecursive = True


def actionSetHelperNodeNoRecur(s, l, st, t):
    """
    Set as helper node which is not recursively processed by editor and renderers
    even if it is unknown
    """
    if t.name != None:
        t.helperNode = True
        t.helperRecursive = False
    else:
        t[0].helperNode = True
        t[0].helperRecursive = False


def actionCutRightWhitespace(s, l, st, t):
    lt = getFirstTerminalNode(t)
    if lt is None:
        return None

    txt = lt.getText()
    for i in xrange(len(txt) - 1, -1, -1):
        if txt[i] not in (u"\t", u" ", u"\n", u"\r"):
            if i < len(txt) - 1:
                lt.text = txt[:i+1]
                lt.recalcStrLength()
                
                t2 = buildSyntaxNode(txt[i+1:], lt.pos + i + 1)
                t.append(t2)
            return t

    return None

  
_CHECK_LEFT_RE = re.compile(ur"[ \t]*$", RE_FLAGS)


def preActCheckNothingLeft(s, l, st, pe):
    # Technically we have to look behind, but this is not supported very
    # well by reg. ex., so we take the reverse string and look ahead
    revText = st.revText
    revLoc = len(s) - l
#     print "--preActCheckNothingLeft4", repr((revLoc, revText[revLoc: revLoc+20]))
    if not _CHECK_LEFT_RE.match(revText, revLoc):
        raise ParseException(s, l, "left of block markup (e.g. table) not empty")


def validateNonEmpty(s, l, st, t):
    if t.strLength == 0:
        raise ParseException(s, l, "matched token must not be empty")




def precTest(s, l, st, pe):
    print "--precTest", repr((l, st, type(pe)))



def createCheckNotIn(tokNames):
    tokNames = frozenset(tokNames)

    def checkNoContain(s, l, st, pe):
        for tn in tokNames:
            if tn in st.nameStack[:-1]:
#                 print "--notcontain exc", repr(st.nameStack[:-1]), tn
                raise ParseException(s, l, "token '%s' is not allowed here" % tn)

    return checkNoContain


def pseudoActionFindMarkup(s, l, st, t):
    if t.strLength == 0:
        return []
    t.name = "plainText"
    return t





# Forward definition of normal content and content in table cells, headings, ...
content = Forward().setName("content")
oneLineContent = Forward().setName("oneLineContent")

tableContentInCell = Forward().setResultsNameNoCopy("tableContentInCell")\
        .setName("tableContentInCell").setParseAction(actionSetHelperNodeRecur)
headingContent = Forward().setResultsNameNoCopy("headingContent").setName("headingContent")
todoContent = Forward().setResultsNameNoCopy("value").setName("value")
titleContent = Forward().setResultsNameNoCopy("title").setName("title")
characterAttributionContent = Forward().setName("characterAttributionContent")

whitespace = buildRegex(ur"[ \t]*")
whitespace = whitespace.setParseAction(actionHideOnEmpty)

whitespaceOrNl = buildRegex(ur"[ \t\n]*")
whitespaceOrNl = whitespaceOrNl.setParseAction(actionHideOnEmpty)


eolOrEot = buildRegex(ur"\n|(?!.)")


def addCreateModeAppendixEntry(l, appendixNode, key, data):
    """
    Add an appendix entry to an existing appendix node or create new node
    """
    if appendixNode is None:
        appendixNode = NonTerminalNode([], l, None)
        appendixNode.entries = [(key, data)]
    else:
        appendixNode.entries.append((key, data))
    
    return appendixNode


def addCreateModeAppendixEntries(l, appendixNode, entrySeq):
    """
    Add multiple appendix entries to an existing appendix node or create new node
    """
    if appendixNode is None:
        appendixNode = NonTerminalNode([], l, None)
        appendixNode.entries = list(entrySeq)
    else:
        appendixNode.entries += list(entrySeq)

    return appendixNode



# The mode appendix for URLs and tables
def actionModeAppendix(s, l, st, t):
    entries = []

    for entry in t.iterFlatByName("entry"):
        key = entry.findFlatByName("key").getText()
        if key.endswith(u":") or key.endswith(u"="):
            key = key[:-1]

        data = entry.findFlatByName("data").getText()
        entries.append((key, data))
        
    t.entries = entries
    return t



modeAppendixEntry = buildRegex(ur"(?:(?![;\|\]=:])\S)+[=:]|(?![;\|\]=:])\S",
        "key") + buildRegex(ur"(?:(?![;\|\]])\S)*", "data")
modeAppendixEntry = modeAppendixEntry.setResultsNameNoCopy("entry")
modeAppendix = modeAppendixEntry + ZeroOrMore(buildRegex(ur";") + modeAppendixEntry)
modeAppendix = modeAppendix.addParseAction(actionModeAppendix)




# -------------------- Simple formatting --------------------

EscapePlainCharPAT = ur"\\"

escapedChar = buildRegex(EscapePlainCharPAT) + buildRegex(ur".", "plainText")
nowikiStandalone = buildRegex(ur"<nowiki ?/>")

italicsStart = buildRegex(ur"''")
italicsStart = italicsStart.setParseStartAction(createCheckNotIn(("italics",)))

italicsEnd = buildRegex(ur"''")

italics = italicsStart + characterAttributionContent + italicsEnd
italics = italics.setResultsNameNoCopy("italics").setName("italics")

boldStart = buildRegex(ur"'''")
boldStart = boldStart.setParseStartAction(createCheckNotIn(("bold",)))

boldEnd = buildRegex(ur"'''")

bold = boldStart + characterAttributionContent + boldEnd
bold = bold.setResultsNameNoCopy("bold").setName("bold")


script = buildRegex(ur"<%") + buildRegex(ur".*?(?=%>)", "code") + \
        buildRegex(ur"%>")
script = script.setResultsNameNoCopy("script")

horizontalLine = buildRegex(ur"----+[ \t]*$", "horizontalLine")\
        .setParseStartAction(preActCheckNothingLeft)


# -------------------- HTML --------------------

htmlTag = buildRegex(ur"</?[A-Za-z][A-Za-z0-9:]*(?:/| [^\n>]*)?>", "htmlTag")

htmlEntity = buildRegex(
        ur"&(?:[A-Za-z0-9]{2,10}|#[0-9]{1,10}|#x[0-9a-fA-F]{1,8});",
        "htmlEntity")

htmlComment = buildRegex(ur"<!-- .*? -->")

# -------------------- Heading --------------------

def actionHeading(s, l, st, t):
    levelStart = len(t.findFlatByName("headingStartTag").getText())
    levelEnd = len(t.findFlatByName("headingEndTag").getText())
        
    t.level = min(levelStart, levelEnd)
    t.contentNode = t.findFlatByName("headingContent")
    if t.contentNode is None:
        raise ParseException(s, l, "a heading needs content")


headingStartTag = buildRegex(ur"^={1,15}", "headingStartTag")

headingEnd = buildRegex(ur"={1,15}", "headingEndTag") + whitespace + \
        buildRegex(ur"\n")

heading = headingStartTag + Optional(buildRegex(ur" ")) + \
        headingContent + headingEnd
heading = heading.setResultsNameNoCopy("heading").setParseAction(actionHeading)



# -------------------- Todo-Entry --------------------

def actionTodoEntry(s, l, st, t):
    t.key = t.findFlatByName("key").getString()
    t.keyComponents = t.key.split(u".")
    t.delimiter = t.findFlatByName("todoDelimiter").getString()
    t.valueNode = t.findFlatByName("value")
    t.todos = [(t.key, t.valueNode)]



todoKey = buildRegex(ur"\b(?:todo|done|wait|action|track|issue|"
        ur"question|project)(?:\.[^:\s]+)?", "key")
# todoKey = todoKey.setParseStartAction(preActCheckNothingLeft)

todoEnd = buildRegex(ur"\n|\||(?!.)")

todoEntry = todoKey + buildRegex(ur":", "todoDelimiter") + todoContent

todoEntry = todoEntry.setResultsNameNoCopy("todoEntry")\
        .setParseAction(actionTodoEntry)
        
todoEntryWithTermination = todoEntry + Optional(buildRegex(ur"\|"))

# Only for LanguageHelper.parseTodoEntry()
todoAsWhole = todoEntry + stringEnd



# -------------------- <pre> html tag, space for <pre>-formatting --------------------


def actionPreHtmlStart(s, l, st, t):
    st.dictStack.getSubTopDict()["inPre"] = True


def actionPreBySpaceStart(s, l, st, t):
    if "preBySpace" in st.nameStack[:-1]:
        # Not the first line with space -> ignore the space
        t.name = None
    elif st.dictStack.getSubTopDict().get("inPre", False):
        # We are inside a HTML "pre"-tag -> space is ordinary text
        raise ParseException(s, l, "pre-space inside <pre>-tag not allowed")
    else:
        # First line with space -> make this a faked "<pre>"-tag
        st.dictStack.getSubTopDict()["inPre"] = True
        t[0].name = "htmlEquivalent"
        t[0].htmlContent = HtmlStartTag(u"pre")

def actionPreBySpaceEnd(s, l, st, t):
    t.name = "htmlEquivalent"
    t.htmlContent = HtmlEndTag(u"pre")


preHtmlStart = buildRegex(ur"<pre(?: [^\n>]*)?>", "htmlTag")\
        .setParseAction(actionPreHtmlStart)

preHtmlEnd = buildRegex(ur"</pre(?: [^\n>]*)?>", "htmlTag")

preHtmlTag = preHtmlStart + content + preHtmlEnd
preHtmlTag = preHtmlTag.setResultsNameNoCopy("preHtmlTag")\
        .setParseAction(actionSetHelperNodeRecur)
#         .setParseStartAction(createCheckNotIn(("preHtmlTag",)))\


preBySpaceStart = buildRegex(ur"^ ")
preBySpaceStart = preBySpaceStart.setParseAction(actionPreBySpaceStart)

preBySpaceEnd = buildRegex(ur"^(?! )|(?!.)") | FollowedBy(preHtmlStart)
preBySpaceEnd.setParseAction(actionPreBySpaceEnd)

preBySpaceFirst = preBySpaceStart + content + preBySpaceEnd
preBySpaceFirst = preBySpaceFirst\
        .setParseStartAction(createCheckNotIn(("preBySpace",)))


preBySpace = preBySpaceFirst | preBySpaceStart
preBySpace = preBySpace.setResultsNameNoCopy("preBySpace")\
        .setParseAction(actionSetHelperNodeRecur)




# -------------------- (un)ordered list --------------------


def actionBulletCombinationStartOrContinuation(s, l, st, t):
    prevCombNorm = st.dictStack.getNamedDict("bulletCombination")\
            .get("prevBulletCombinationNorm", u"")
    newComb = t[0].getText()
    t[0].helperNode = True

    # For definition lists the "!" generates the enclosing "dl"-tag
    # it is only used internally and not part of MediaWiki syntax
    newCombNorm = newComb.replace(u":", u"!:").replace(u";", u"!;")

    lastBulletChar = newCombNorm[-1]
    st.dictStack.getNamedDict("bulletCombination")\
            ["prevBulletCombinationNorm"] = newCombNorm

    result = [t[0]]
    # Eliminate equal prefix
    while prevCombNorm != u"" and newCombNorm != u"" and prevCombNorm[0] == newCombNorm[0]:
        prevCombNorm = prevCombNorm[1:]
        newCombNorm = newCombNorm[1:]


    while prevCombNorm != u"":
        n = TerminalNode(u"", l, "htmlEquivalent")
        bulletChar = prevCombNorm[-1]
        endTag = {
                u"*": u"ul",
                u"#": u"ol",
                u";": u"dt",
                u":": u"dd",
                u"!": u"dl",
            }[bulletChar]

        n.htmlContent = HtmlEndTag(endTag)

        result.append(n)
        prevCombNorm = prevCombNorm[:-1]

    startTag = u""
    while newCombNorm != u"":
        n = TerminalNode(u"", l, "htmlEquivalent")
        bulletChar = newCombNorm[0]
        startTag = {
                u"*": u"ul",
                u"#": u"ol",
                u";": u"dt",
                u":": u"dd",
                u"!": u"dl",
            }[bulletChar]
        
        n.htmlContent = HtmlStartTag(startTag)
        result.append(n)
        newCombNorm = newCombNorm[1:]

    if lastBulletChar in u"*#":
        n = TerminalNode(u"", l, "htmlEquivalent")
        n.htmlContent = HtmlEmptyTag("li")
        result.append(n)
    elif lastBulletChar == u":":
        if startTag != u"dd":
            # If the last bullet character ':' wasn't part of the common
            # prefix it was processed as last character of newCombNorm
            # and "dd" was set as startTag. In this case the "dd" shouldn't
            # be closed and reopened
            n = TerminalNode(u"", l, "htmlEquivalent")
            n.htmlContent = HtmlEndTag(u"dd")
            result.append(n)

            n = TerminalNode(u"", l, "htmlEquivalent")
            n.htmlContent = HtmlStartTag(u"dd")
            result.append(n)
    elif lastBulletChar == u";":
        if startTag != u"dt":
            # Same logic as above
            n = TerminalNode(u"", l, "htmlEquivalent")
            n.htmlContent = HtmlEndTag(u"dt")
            result.append(n)

            n = TerminalNode(u"", l, "htmlEquivalent")
            n.htmlContent = HtmlStartTag(u"dt")
            result.append(n)

    return result


def actionBulletCombinationEnd(s, l, st, t):
    prevCombNorm = st.dictStack.getNamedDict("bulletCombination")\
            .get("prevBulletCombinationNorm", u"")

    t[0].helperNode = True
    result = [t[0]]

    while prevCombNorm != u"":
        n = TerminalNode(u"", l, "htmlEquivalent")
        bulletChar = prevCombNorm[-1]
        endTag = {
                u"*": u"ul",
                u"#": u"ol",
                u";": u"dt",
                u":": u"dd",
                u"!": u"dl",
            }[bulletChar]

        n.htmlContent = HtmlEndTag(endTag)

        result.append(n)
        prevCombNorm = prevCombNorm[:-1]
    
    return result



bulletCombinationStart = buildRegex(ur"^[\*#;:]+", "bulletCombinationStart")\
        .setParseAction(actionBulletCombinationStartOrContinuation)

bulletCombinationContinuation = bulletCombinationStart\
        .setResultsName("bulletCombinationContinuation")\
        .setParseAction(actionBulletCombinationStartOrContinuation)


bulletCombinationStart = bulletCombinationStart
        


bulletCombinationEnd = buildRegex(ur"^(?![\*#:;])|(?!.)", "bulletCombinationEnd")\
        .setParseAction(actionBulletCombinationEnd)

bulletCombination = bulletCombinationStart + content + bulletCombinationEnd
bulletCombination = bulletCombination.setResultsNameNoCopy("bulletCombination")\
        .setParseAction(actionSetHelperNodeRecur)\
        .setParseStartAction(createCheckNotIn(("bulletCombination",)))


def preActNewLinesParagraph(s, l, st, pe):
    if st.dictStack.getSubTopDict().get("inPre", False):
        raise ParseException(s, l, "Newlines aren't paragraph inside <pre> tag")


def preActNewLineWhitespace(s, l, st, pe):
    if st.dictStack.getSubTopDict().get("inPre", False):
        raise ParseException(s, l, "Newline isn't whitespace inside <pre> tag")




# Only an empty line
fakeIndentation = buildRegex(ur"^[ \t]+$")

newLine = buildRegex(ur"\n") + Optional(fakeIndentation)



newLinesParagraph = newLine + OneOrMore(newLine)
newLinesParagraph = newLinesParagraph.setResultsNameNoCopy("newParagraph")\
        .setParseStartAction(preActNewLinesParagraph)


newLineWhitespace = newLine
newLineWhitespace = newLineWhitespace.setResultsName("whitespace")\
        .setParseStartAction(preActNewLineWhitespace)





# -------------------- Table --------------------


# TODO: Support HTML attributes

def actionSetTableContentInCell(s, l, st, t):
    contentNode = t.findFlatByName("tableContentInCell")


def actionTableCaption(s, l, st, t):
    sn = TerminalNode(u"", l, "htmlEquivalent")
    sn.htmlContent = HtmlStartTag(u"caption")

    attNode = t.findFlatByName("tableCaptionHtmlAttributes")
    if attNode is not None:
        sn.htmlContent.addEscapedAttributes(attNode.htmlAttributes)

    en = TerminalNode(u"", l, "htmlEquivalent")
    en.htmlContent = HtmlEndTag(u"caption")
    
    t.prepend(sn)
    t.append(en)
    

def actionTableRow(s, l, st, t):
    sn = TerminalNode(u"", l, "htmlEquivalent")
    sn.htmlContent = HtmlStartTag(u"tr")

    attNode = t.findFlatByName("tableRowHtmlAttributes")
    if attNode is not None:
        sn.htmlContent.addEscapedAttributes(attNode.htmlAttributes)

    en = TerminalNode(u"", l, "htmlEquivalent")
    en.htmlContent = HtmlEndTag(u"tr")

    t.prepend(sn)
    t.append(en)


def actionTableHeaderCell(s, l, st, t):
    sn = TerminalNode(u"", l, "htmlEquivalent")
    sn.htmlContent = HtmlStartTag(u"th")

    attNode = t.findFlatByName("tableCellHtmlAttributes")
    if attNode is not None:
        sn.htmlContent.addEscapedAttributes(attNode.htmlAttributes)

    en = TerminalNode(u"", l, "htmlEquivalent")
    en.htmlContent = HtmlEndTag(u"th")

    t.prepend(sn)
    t.append(en)
    

def actionTableCell(s, l, st, t):
    sn = TerminalNode(u"", l, "htmlEquivalent")
    sn.htmlContent = HtmlStartTag(u"td")

    attNode = t.findFlatByName("tableCellHtmlAttributes")
    if attNode is not None:
        sn.htmlContent.addEscapedAttributes(attNode.htmlAttributes)

    en = TerminalNode(u"", l, "htmlEquivalent")
    en.htmlContent = HtmlEndTag(u"td")

    t.prepend(sn)
    t.append(en)


def actionTableMediaWiki(s, l, st, t):
    # TODO: Problem with folding
    sn = TerminalNode(u"", l, "htmlEquivalent")
    sn.htmlContent = HtmlStartTag(u"table")
    
    attNode = t.findFlatByName("tableHtmlAttributes")
    if attNode is not None:
        sn.htmlContent.addEscapedAttributes(attNode.htmlAttributes)

    en = TerminalNode(u"", l, "htmlEquivalent")
    en.htmlContent = HtmlEndTag(u"table")

    t.prepend(sn)
    t.append(en)
    

def actionGenericHtmlAttributes(s, l, st, t):
    htmlAttributes = []
    
    for entry in t.iterFlatByName("htmlAttribute"):
        key = entry.findFlatByName("htmlAttributeKey").getText()
        value = entry.findFlatByName("htmlAttributeValue").getText()
        htmlAttributes.append((key, value))

    t.htmlAttributes = htmlAttributes
    t.helperNode = True
    t.helperRecursive = False


# The following HTML tokens are needed later

htmlAttributeValueQuoted = buildRegex(ur'"') + \
        buildRegex(ur'[^"\n\t]*', "htmlAttributeValue") + \
        buildRegex(ur'"')
        
htmlAttributeValueNotQuoted = buildRegex(ur'[^"\n\t ]+', "htmlAttributeValue")

htmlAttribute = whitespace + buildRegex(ur"[A-Za-z0-9]+", "htmlAttributeKey") + \
        whitespace + buildRegex(ur"=") + whitespace + \
        (htmlAttributeValueQuoted | htmlAttributeValueNotQuoted)

htmlAttribute = htmlAttribute.setResultsNameNoCopy("htmlAttribute")


tableAttributeStop = whitespace + buildRegex(ur"\|")

genericHtmlAttributes = OneOrMore(htmlAttribute)
genericHtmlAttributes = genericHtmlAttributes\
        .setResultsNameNoCopy("genericHtmlAttributes")\
        .setParseAction(actionGenericHtmlAttributes)

tableStart = buildRegex(ur"^[ \t]*\{\|") + whitespace + \
        Optional(genericHtmlAttributes.setResultsName("tableHtmlAttributes")) + \
        whitespaceOrNl

tableEnd = buildRegex(ur"^[ \t]*\|\}[ \t]*(?:\n|$)")

tableCaption = buildRegex(ur"^[ \t]*\|\+") + whitespace + \
        Optional(genericHtmlAttributes.setResultsName("tableCaptionHtmlAttributes") +
        tableAttributeStop) + whitespaceOrNl + tableContentInCell
tableCaption = tableCaption.setParseAction(actionTableCaption)

tableHeaderCell = buildRegex(ur"^[ \t]*!|!!") + whitespace + \
        Optional(genericHtmlAttributes.setResultsName("tableCellHtmlAttributes") +
        tableAttributeStop) + whitespaceOrNl + tableContentInCell
tableHeaderCell = tableHeaderCell.setParseAction(actionTableHeaderCell)\
        .setParseAction(actionSetHelperNodeRecur).addParseAction(actionTableHeaderCell)

tableCell = buildRegex(ur"^[ \t]*\|(?![\}+\-])|\|\|") + whitespace + \
        Optional(genericHtmlAttributes.setResultsName("tableCellHtmlAttributes") +
        tableAttributeStop) + whitespaceOrNl + tableContentInCell
tableCell = tableCell.setResultsNameNoCopy("tableCell")\
        .setParseAction(actionSetHelperNodeRecur).addParseAction(actionTableCell)

tableRow = buildRegex(ur"^[ \t]*\|-") + whitespace + \
        Optional(genericHtmlAttributes.setResultsName("tableRowHtmlAttributes")) + \
        whitespaceOrNl + OneOrMore(tableCell | tableHeaderCell)

tableRow = tableRow.setResultsNameNoCopy("tableRow")\
        .setParseAction(actionSetHelperNodeRecur).addParseAction(actionTableRow)

tableFirstRow = Optional(buildRegex(ur"^[ \t]*\|-") + whitespace + \
        Optional(genericHtmlAttributes.setResultsName("tableRowHtmlAttributes")) + \
        whitespaceOrNl) + OneOrMore(tableCell | tableHeaderCell)
        
tableFirstRow = tableFirstRow.setResultsNameNoCopy("tableRow")\
        .setParseAction(actionSetHelperNodeRecur).addParseAction(actionTableRow)

tableMediaWiki = tableStart + Optional(tableCaption) + \
        tableFirstRow + ZeroOrMore(tableRow) + tableEnd
tableMediaWiki = tableMediaWiki.setResultsNameNoCopy("tableMediaWiki")\
        .setParseAction(actionSetHelperNodeRecur).addParseAction(actionTableMediaWiki)

tableElementMediaWiki = buildRegex(ur"^[ \t]*[\|!]|\|\|")



# -------------------- Suppress highlighting and no export --------------------

# suppressHighlightingMultipleLines = buildRegex(ur"<<[ \t]*\n")\
#         .setParseStartAction(preActCheckNothingLeft) + \
#         buildRegex(ur".*?(?=^[ \t]*>>[ \t]*(?:\n|$))", "plainText") + \
#         buildRegex(ur"^[ \t]*>>[ \t]*(?:\n|$)")

suppressHighlighting = buildRegex(ur"<nowiki>") + \
        buildRegex(ur".*?(?=</nowiki>)", "plainText") + buildRegex(ur"</nowiki>")





# -------------------- No export area--------------------


def actionNoExport(s, l, st, t):
    # Change name to reduce work when interpreting
    t.name = "noExport"


noExportSingleLineEnd = buildRegex(ur"</hide>")


noExportSingleLine = buildRegex(ur"<hide>") + content + noExportSingleLineEnd
noExportSingleLine = noExportSingleLine.setResultsNameNoCopy("noExportSl")\
        .setParseStartAction(createCheckNotIn(("noExportSl",)))\
        .setParseAction(actionNoExport)


# -------------------- <body> html tag --------------------

def actionBodyHtmlTag(s, l, st, t):
    t.content = t.findFlatByName("bodyHtmlText").getString()


bodyHtmlStart = buildRegex(ur"<body(?: [^\n>]*)?>", "htmlTag")
 
bodyHtmlEnd = buildRegex(ur"</body>", "htmlTag")

bodyHtmlText = buildRegex(ur".*?(?=" + bodyHtmlEnd.getPattern() + ")",
        "bodyHtmlText")


bodyHtmlTag = bodyHtmlStart + bodyHtmlText + bodyHtmlEnd
bodyHtmlTag = bodyHtmlTag.setResultsNameNoCopy("bodyHtmlTag")\
        .setParseAction(actionBodyHtmlTag)



# -------------------- Wikiwords and URLs --------------------

BracketStart = u"[["
BracketStartPAT = ur"\[\["

BracketEnd = u"]]"
BracketEndPAT = ur"\]\]"
# WikiWordNccPAT = ur"/?(?:/?[^\\/\[\]\|\000-\037=:;#!]+)+" # ur"[\w\-\_ \t]+"

# Single part of subpage path
WikiWordPathPartPAT = ur"(?!\.\.)[^\\/\[\]\|\000-\037=:;#!]+"
WikiPageNamePAT = WikiWordPathPartPAT + "(?:/" + WikiWordPathPartPAT + ")*"

# Begins with dotted path parts which mean to go upward in subpage path
WikiWordDottedPathPAT = ur"\.\.(?:/\.\.)*(?:/" + WikiWordPathPartPAT + ")*"
WikiWordNonDottedPathPAT = ur"/{0,2}" + WikiPageNamePAT

WikiWordNccPAT = WikiWordDottedPathPAT + ur"|" + WikiWordNonDottedPathPAT

WikiWordTitleStartPAT = ur"\|"
WikiWordAnchorStart = u"!"
WikiWordAnchorStartPAT = ur"!"

# Bracket start, escaped for reverse RE pattern (for autocompletion)
BracketStartRevPAT = ur"\[\["
# Bracket end, escaped for reverse RE pattern (for autocompletion)
BracketEndRevPAT = ur"\]\]"

WikiWordNccRevPAT = ur"[^\\\[\]\|\000-\037=:;#!]+?"  # ur"[\w\-\_ \t.]+?"


UrlPAT = ur'(?:(?:https?|ftp|rel|wikirel)://|mailto:|Outlook:\S|wiki:/|file:/)'\
        ur'(?:(?![.,;:!?)]+(?:["\s]|$))[^"\s|\]<>])*'


# UrlInBracketsPAT = ur'(?:(?:https?|ftp|rel|wikirel)://|mailto:|Outlook:\S|wiki:/|file:/)'\
#         ur'(?:(?![ \t]+[|\]])(?: |[^"\s|\]<>]))*'


bracketStart = buildRegex(BracketStartPAT)
bracketEnd = buildRegex(BracketEndPAT)


UnescapeExternalFragmentRE   = re.compile(ur"#(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)


def reThrough(matchobj):
    return matchobj.group(1)


def actionSearchFragmentExtern(s, l, st, t):
    """
    Called to unescape external fragment of wikiword.
    """
    lt2 = getFirstTerminalNode(t)
    if lt2 is None:
        return None
    
    lt2.unescaped = UnescapeExternalFragmentRE.sub(ur"\1", lt2.text)


UnescapeStandardRE = re.compile(EscapePlainCharPAT + ur"(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)

def actionSearchFragmentIntern(s, l, st, t):
    lt2 = getFirstTerminalNode(t)
    if lt2 is None:
        return None

    lt2.unescaped = UnescapeStandardRE.sub(ur"\1", lt2.text)



def resolveWikiWordLink(link, basePage):
    """
    If using subpages this is used to resolve a link to the right wiki word
    relative to basePage on which the link is placed.
    It returns the absolute link (page name).
    """
    return _TheHelper.resolvePrefixSilenceAndWikiWordLink(link, basePage)[2]
   



def actionWikiWordNcc(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]

    if t.wikiWord is not None:
        t.wikiWord = resolveWikiWordLink(t.wikiWord.getString(),
                wikiFormatDetails.basePage)
    else:
        t.wikiWord = resolveWikiWordLink(u".", wikiFormatDetails.basePage)

    if t.wikiWord == u"":
        raise ParseException(s, l, "Subpage resolution of wikiword failed")

    if t.wikiWord in wikiFormatDetails.wikiDocument.getNccWordBlacklist():
        raise ParseException(s, l, "Non-CamelCase word is in blacklist")

    t.titleNode = t.findFlatByName("title")
    
    titleTrailNode = t.findFlatByName("titleTrail")
    if (titleTrailNode is not None):
        if t.titleNode is None:
            t.titleNode = NonTerminalNode([
                    TerminalNode(t.wikiWord, l, "plainText")], l, "title")

        t.titleNode.append(buildSyntaxNode(
                titleTrailNode.getString(), titleTrailNode.pos, "plainText"))
        titleTrailNode.name = None

    t.fragmentNode = t.findFlatByName("searchFragment")
    if t.fragmentNode is not None:
        t.searchFragment = t.fragmentNode.unescaped
    else:
        t.searchFragment = None
    
    t.anchorLink = t.findFlatByName("anchorLink")
    if t.anchorLink is not None:
        t.anchorLink = t.anchorLink.getString()



def preActCheckWikiWordCcAllowed(s, l, st, pe):
    try:
        wikiFormatDetails = st.dictStack["wikiFormatDetails"]
        
        if not wikiFormatDetails.withCamelCase:
            raise ParseException(s, l, "CamelCase words not allowed here")
    except KeyError:
        pass


def actionWikiWordCc(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    if t.wikiWord is not None:
        wikiFormatDetails = st.dictStack["wikiFormatDetails"]

        t.wikiWord = resolveWikiWordLink(t.wikiWord.getString(),
                wikiFormatDetails.basePage)

        if t.wikiWord == u"":
            raise ParseException(s, l, "Subpage resolution of wikiword failed")

        try:
#             wikiFormatDetails = st.dictStack["wikiFormatDetails"]
            
            if t.wikiWord in wikiFormatDetails.wikiDocument.getCcWordBlacklist():
                raise ParseException(s, l, "CamelCase word is in blacklist")
        except KeyError:
            pass

    t.titleNode = None

    t.fragmentNode = t.findFlatByName("searchFragment")
    if t.fragmentNode is not None:
        t.searchFragment = t.fragmentNode.unescaped
    else:
        t.searchFragment = None

    t.anchorLink = t.findFlatByName("anchorLink")
    if t.anchorLink is not None:
        t.anchorLink = t.anchorLink.getString()


def parseGlobalAppendixEntries(s, l, st, t, ignore=()):
    """
    Handles the global appendix attributes that can be set for any
    item that supports appendices
    """
    t.cssClass = None
    t.text_align = None

    for key, data in t.entries:
        # Skip keys that have been redefined in the calling appendix
        if key in ignore:
            continue

        # CSS classes are designated by "s" or "class". They will result in the
        # css class(es) being applied to the element. Multiple classes can be
        # separated by comma (,)
        # E. g. "s=foo" uses class "foo". The '=' can be omitted for the
        # short form "s", therefore "sfoo" does the same. The same is also:
        # "class=foo", "s:foo" and "class:foo".
        
        # The longer form is recommended, the short "s" e.g. does not work
        # in appendices for image URLs due to a name clash
        if key == u"s" or key == u"class":
            t.cssClass = data.replace(u",", u" ")
        elif key == u"A" or key == u"align":
            if data in (u"l", u"c", u"r", u"left", u"center", u"right"):
                t.text_align = data

    return s, l, st, t



def actionExtractableWikiWord(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    if t.wikiWord is not None:
        t.wikiWord = t.wikiWord.getString()



def actionUrlLink(s, l, st, t):
    if t.name == "urlLinkBare":
        t.bracketed = False
    else:
        t.bracketed = True
    
    t.name = "urlLink"        
    t.appendixNode = t.findFlatByName("urlModeAppendix")
    # In MediaWiki, image links have another syntax. Therefore create appendix
    # to declare link as real link
    t.appendixNode = addCreateModeAppendixEntry(l, t.appendixNode, u"l", u"")
    t.coreNode = t.findFlatByName("url")

    # Valid URL but may differ from original input (does not for MediaWiki,
    # spaces aren't allowed)
    t.url = t.coreNode.getString()
    t.titleNode = t.findFlatByName("title")
    


def actionAnchorDef(s, l, st, t):
    t.anchorLink = t.findFlatByName("anchor").getString()


def actionUrlModeAppendix(s, l, st, t):
    s, l, st, t = parseGlobalAppendixEntries(s, l, st, t, ignore=(u"s",))
    
#     t.border = None
# 
#     for key, data in t.entries:
#         if key == u"b":
#             if data.endswith(u"px"):
#                 t.border = data
#             else:
#                 t.border = "{0}px".format(data)



# _IMAGE_OPTION_KEYWORD_TO_APPENDIX = {
        

def actionImageUrl(s, l, st, t):
    # Process options for the URL. Currently only a few options are really handled
    # TODO: Process more
    t.name = "urlLink"
    t.appendixNode = t.findFlatByName("urlModeAppendix")
    t.coreNode = t.findFlatByName("url")
    t.url = t.coreNode.getString()
    t.titleNode = t.findFlatByName("title")
    
    modeAppendixEntries = []
    cssClasses = []
    
    for node in t.iterFlatByName("imageUrlOption"):
        subNode = node.findFlatByName("keyword")
        if subNode is not None:
            key = subNode.getString()
            if key in (u"left", u"center", u"right", u"top", u"middle", u"bottom"):
                modeAppendixEntries.append((u"align", key))
            elif key == u"upright":
                modeAppendixEntries.append((u"upright", u"1"))
                
            continue
        
        subNode = node.findFlatByName("key")
        if subNode is not None:
            key = subNode.getString()
            value = node.findFlatByName("value").getString()
            if key == "class":
                cssClasses.append(value)
            
            continue
        
        subNode = node.findFlatByName("pixelsize")
        if subNode is not None:
            psStr = subNode.getString().replace(u"px", u"")
            modeAppendixEntries.append((u"r", psStr))
        
        # Pixel size options are currently not processed

    # Tell exporter that this is an image url
    modeAppendixEntries.append((u"i", u""))

    t.appendixNode = addCreateModeAppendixEntries(l, t.appendixNode,
            modeAppendixEntries)

    if len(cssClasses) > 0:
        t.cssClass = u" ".join(cssClasses)



searchFragmentExtern = buildRegex(ur"#") + \
        buildRegex(ur"(?:(?:#.)|[^ \t\n#])+", "searchFragment")\
        .setParseAction(actionSearchFragmentExtern)

searchFragmentIntern = buildRegex(ur"#") + buildRegex(ur"(?:(?:" + EscapePlainCharPAT +
        ur".)|(?!" + WikiWordTitleStartPAT +
        ur"|" +  BracketEndPAT + ur").)+", "searchFragment")\
        .setParseAction(actionSearchFragmentIntern)

wikiWordAnchorLink = buildRegex(WikiWordAnchorStartPAT) + \
        buildRegex(ur"[A-Za-z0-9\_]+", "anchorLink")


title = buildRegex(WikiWordTitleStartPAT + ur"[ \t]*") + titleContent    # content.setResultsName("title")


wikiWordNccCore = buildRegex(WikiWordNccPAT, "word")

wikiWordNccWithWord = bracketStart + \
        wikiWordNccCore.copy().addParseAction(actionCutRightWhitespace) + \
        Optional(MatchFirst([searchFragmentIntern, wikiWordAnchorLink])) + whitespace + \
        Optional(title) + bracketEnd + Optional(buildRegex(ur"\w+", "titleTrail"))

wikiWordNccSearchInPage = bracketStart + \
        searchFragmentIntern + whitespace + \
        Optional(title) + bracketEnd + Optional(buildRegex(ur"\w+", "titleTrail"))

wikiWordNcc = wikiWordNccWithWord | wikiWordNccSearchInPage

wikiWordNcc = wikiWordNcc.setResultsNameNoCopy("wikiWord").setName("wikiWordNcc")\
        .setParseAction(actionWikiWordNcc)


anchorDef = buildRegex(ur"^[ \t]*anchor:[ \t]*") + buildRegex(ur"[A-Za-z0-9\_]+",
        "anchor") + buildRegex(ur"\n")
anchorDef = anchorDef.setResultsNameNoCopy("anchorDef").setParseAction(actionAnchorDef)


AnchorRE = re.compile(ur"^[ \t]*anchor:[ \t]*(?P<anchorValue>[A-Za-z0-9\_]+)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)



urlModeAppendix = modeAppendix.setResultsName("urlModeAppendix").addParseAction(
        actionUrlModeAppendix)

urlWithAppend = buildRegex(UrlPAT, "url") + Optional(buildRegex(ur">") + \
        urlModeAppendix)

urlWithAppendInBrackets = buildRegex(UrlPAT, "url") + Optional(buildRegex(ur">") + \
        urlModeAppendix)


urlBare = urlWithAppend.setResultsName("urlLinkBare")
urlBare = urlBare.setParseAction(actionUrlLink)

urlBracketEnd = buildRegex(ur"\]")

urlTitled = buildRegex(ur"\[") + urlWithAppendInBrackets + \
        Optional(buildRegex(ur" ") + whitespace + titleContent) + whitespace + \
        urlBracketEnd

urlTitled = urlTitled.setResultsNameNoCopy("urlLinkBracketed").setParseAction(actionUrlLink)

urlRef = urlTitled | urlBare


# Correct but unsupported "pixelsize" syntax:
#         buildRegex(ur"x?[0-9]+px|[0-9]+x[0-9]+px", "pixelsize") |


imageUrlOption = buildRegex(ur"\|") + ( buildRegex(ur"border|frameless|frame|upright|thumb|"
        ur"left|right|center|none|baseline|sub|super|top|text-top|middle|bottom|text-bottom", "keyword") |
        buildRegex(ur"[0-9]+px(?:x[0-9]+px)?", "pixelsize") |
        ( buildRegex(ur"thumb|link|alt|page|class", "key") + buildRegex(ur"=") + 
            buildRegex(ur"[^\n\t\]|]*", "value") )
        )
imageUrlOption = imageUrlOption.setResultsNameNoCopy("imageUrlOption")

imageUrl = bracketStart + urlWithAppendInBrackets + whitespace + \
        ZeroOrMore(imageUrlOption) + Optional(title) + bracketEnd

imageUrl = imageUrl.setResultsNameNoCopy("imageUrl").setParseAction(actionImageUrl)



wikiWord = wikiWordNcc



# Needed for _TheHelper.extractWikiWordFromLink()

extractableWikiWord = (wikiWordNccCore | wikiWordNcc) + stringEnd
extractableWikiWord = extractableWikiWord.setResultsNameNoCopy("extractableWikiWord")\
        .setParseAction(actionExtractableWikiWord).optimize(("regexcombine",))\
        .parseWithTabs()


wikiPageNameRE = re.compile(ur"^" + WikiPageNamePAT + ur"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


wikiLinkCoreRE = re.compile(ur"^" + WikiWordNccPAT + ur"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)



# -------------------- Footnotes --------------------

# TODO: Emulate MediaWiki cite extension

footnotePAT = ur"[0-9]+"

def preActCheckFootnotesAllowed(s, l, st, pe):
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]
    
    if wikiFormatDetails.wikiLanguageDetails.footnotesAsWws:
        raise ParseException(s, l, "CamelCase words not allowed here")


def actionFootnote(s, l, st, t):
    t.footnoteId = t.findFlatByName("footnoteId").getString()


footnote = bracketStart + buildRegex(footnotePAT, "footnoteId") + bracketEnd
footnote = footnote.setResultsNameNoCopy("footnote")\
        .setParseStartAction(preActCheckFootnotesAllowed)\
        .setParseAction(actionFootnote)


footnoteRE = re.compile(ur"^" + footnotePAT + ur"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# -------------------- Attributes (=properties) and insertions --------------------

# Unmodified because not supported by MediaWiki but needed by WikidPad

def actionAttrInsValueQuoteStart(s, l, st, t):
    st.dictStack.getSubTopDict()["attrInsValueQuote"] = t[0].text

def actionAttrInsValueQuoteEnd(s, l, st, t):
    if t[0].text != st.dictStack.getSubTopDict().get("attrInsValueQuote"):
        raise ParseException(s, l, "End quote of attribute/insertion does not match start")


def pseudoActionAttrInsQuotedValue(s, l, st, t):
    if t.strLength == 0:
        return []
    t.name = "value"
    return t


def actionAttribute(s, l, st, t):
    key = t.findFlatByName("key").getString()
    t.key = key
    t.keyComponents = t.key.split(u".")
    t.attrs = [(key, vNode.getString()) for vNode in t.iterFlatByName("value")]


def actionInsertion(s, l, st, t):
    t.key = t.findFlatByName("key").getString()
    t.keyComponents = t.key.split(u".")
    values = list(vNode.getString() for vNode in t.iterFlatByName("value"))
    t.value = values[0]
    del values[0]
    t.appendices = values



attrInsQuote = buildRegex(ur"\"+|'+|/+|\\+")
attrInsQuoteStart = attrInsQuote.copy()\
        .setParseAction(actionAttrInsValueQuoteStart)
attrInsQuoteEnd = attrInsQuote.copy()\
        .setParseAction(actionAttrInsValueQuoteEnd)

attrInsQuotedValue = FindFirst([], attrInsQuoteEnd)\
        .setPseudoParseAction(pseudoActionAttrInsQuotedValue)

# attrInsNonQuotedValue = buildRegex(ur"[\w\-\_ \t:,.!?#%|/]*", "value")
attrInsNonQuotedValue = buildRegex(ur"(?:[ \t]*[\w\-\_=:,.!?#%|/]+)*", "value")


attrInsValue = whitespace + ((attrInsQuoteStart + attrInsQuotedValue + \
        attrInsQuoteEnd) | attrInsNonQuotedValue)

attrInsKey = buildRegex(ur"[\w\-\_\.]+", "key")

attribute = bracketStart + whitespace + attrInsKey + \
        buildRegex(ur"[ \t]*[=:]") + attrInsValue + \
        ZeroOrMore(buildRegex(ur";") + attrInsValue) + whitespace + bracketEnd
attribute = attribute.setResultsNameNoCopy("attribute").setParseAction(actionAttribute)


insertion = bracketStart + buildRegex(ur":") + whitespace + attrInsKey + \
        buildRegex(ur"[ \t]*[=:]") + attrInsValue + \
        ZeroOrMore(buildRegex(ur";") + attrInsValue) + whitespace + bracketEnd
insertion = insertion.setResultsNameNoCopy("insertion").setParseAction(actionInsertion)



# -------------------- Additional regexes to provide --------------------

# Needed for auto-bullet/auto-unbullet functionality of editor
BulletRE        = re.compile(ur"^(?P<indentBullet>[ \t]*)"
        ur"(?P<preLastBullet>[\*#;: \t]*)"
        ur"(?P<lastBullet>[\*#;:])(?P<lastBulletWhite>[ \t]*)",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Needed for handleRewrapText
EmptyLineRE     = re.compile(ur"^[ \t\r\n]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)




# Reverse REs for autocompletion

RevWikiWordRE2     = re.compile(ur"^" + WikiWordNccRevPAT + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevAttributeValue     = re.compile(
        ur"^([\w\-\_ \t:;,.!?#/|]*?)([ \t]*[=:][ \t]*)([\w\-\_ \t\.]+?)" +
        BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


RevTodoKeyRE = re.compile(ur"^(?:[^:\s]{0,40}\.)??"
        ur"(?:odot|enod|tiaw|noitca|kcart|eussi|noitseuq|tcejorp)",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevTodoValueRE = re.compile(ur"^[^\n:]{0,30}:" + RevTodoKeyRE.pattern[1:],
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevWikiWordAnchorRE2 = re.compile(ur"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" + 
        WikiWordAnchorStartPAT + BracketEndRevPAT + ur"(?P<wikiWord>" + 
        WikiWordNccRevPAT + ur")" + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


# Simple todo RE for autocompletion.
ToDoREWithCapturing = re.compile(ur"^([^:\s]+):[ \t]*(.+?)$",
        re.DOTALL | re.UNICODE | re.MULTILINE)



# For auto-link mode relax
AutoLinkRelaxSplitRE = re.compile(r"[\W]+", re.IGNORECASE | re.UNICODE)

AutoLinkRelaxJoinPAT = ur"[\W]+"
AutoLinkRelaxJoinFlags = re.IGNORECASE | re.UNICODE



# For spell checking
TextWordRE = re.compile(ur"(?P<negative>[0-9]+|"+ UrlPAT + u")|\b[\w']+",
        re.DOTALL | re.UNICODE | re.MULTILINE)





# -------------------- End tokens --------------------


TOKEN_TO_END = {
        "bold": boldEnd,
        "italics": italicsEnd,
        "wikiWord": bracketEnd,
        "urlLinkBracketed": urlBracketEnd,
        "imageUrl": bracketEnd,
        "tableMediaWiki": tableEnd,
        "bulletCombination": bulletCombinationEnd,
        "preHtmlTag": preHtmlEnd,
        "preBySpace": preBySpaceEnd,
        "heading": headingEnd,
        "todoEntry": todoEnd,
        "noExportSl": noExportSingleLineEnd
    }


def chooseEndToken(s, l, st, pe):
    """
    """
    for tokName in reversed(st.nameStack):
        end = TOKEN_TO_END.get(tokName)
        if end is not None:
            return end

    return stringEnd


endToken = Choice([stringEnd]+TOKEN_TO_END.values(), chooseEndToken)

endTokenInTable = endToken | tableElementMediaWiki

endTokenInTitle = endToken | buildRegex(ur"\n")

endTokenInCharacterAttribution = endToken | heading



# -------------------- Content definitions --------------------


findMarkupInCell = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlighting,
        urlRef, imageUrl, insertion, escapedChar, nowikiStandalone, footnote, wikiWord,
        newLinesParagraph, newLineWhitespace,
        bodyHtmlTag, htmlTag, htmlEntity, htmlComment, bulletCombination,
        bulletCombinationContinuation], endTokenInTable)
findMarkupInCell = findMarkupInCell.setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInTable) + findMarkupInCell)
temp = temp.leaveWhitespace().parseWithTabs()
tableContentInCell << temp



findMarkupInTitle = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlighting,
        urlRef, imageUrl, insertion, escapedChar, nowikiStandalone, footnote, bodyHtmlTag, htmlTag,
        htmlEntity, htmlComment],
        endTokenInTitle)
findMarkupInTitle = findMarkupInTitle.setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInTitle) + findMarkupInTitle)
temp = temp.leaveWhitespace().parseWithTabs()
titleContent << temp



findMarkupInHeading = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlighting,
        urlRef, imageUrl, insertion, escapedChar, nowikiStandalone, footnote, wikiWord, bodyHtmlTag,
        htmlTag, htmlEntity, htmlComment], endToken)
findMarkupInHeading = findMarkupInHeading.setPseudoParseAction(
        pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endToken) + findMarkupInHeading)
temp = temp.leaveWhitespace().parseWithTabs()
headingContent << temp



findMarkupInTodo = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlighting,
        urlRef, imageUrl, attribute, insertion, escapedChar, nowikiStandalone, footnote, wikiWord,
        bodyHtmlTag, htmlTag, htmlEntity, htmlComment], endToken)
findMarkupInTodo = findMarkupInTodo.setPseudoParseAction(
        pseudoActionFindMarkup)

temp = OneOrMore(NotAny(endToken) + findMarkupInTodo)
temp = temp.leaveWhitespace().parseWithTabs()
todoContent << temp
oneLineContent << temp



findMarkupInCharacterAttribution = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlighting, urlRef, imageUrl,
        attribute, insertion, escapedChar, nowikiStandalone, footnote, wikiWord,
        newLinesParagraph, newLineWhitespace,
        todoEntryWithTermination, anchorDef, preBySpace, preHtmlTag, bodyHtmlTag,
        htmlTag, htmlEntity, htmlComment, 
        tableMediaWiki],
        endTokenInCharacterAttribution)
findMarkupInCharacterAttribution = findMarkupInCharacterAttribution\
        .setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInCharacterAttribution) +
        findMarkupInCharacterAttribution)
temp = temp.leaveWhitespace().parseWithTabs()
characterAttributionContent << temp



findMarkup = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlighting, urlRef, imageUrl,
        attribute, insertion, escapedChar, nowikiStandalone, footnote, wikiWord,
        newLinesParagraph, newLineWhitespace, heading,
        todoEntryWithTermination, anchorDef, preBySpace, preHtmlTag, bodyHtmlTag,
        htmlTag, htmlEntity, htmlComment,
        bulletCombination, bulletCombinationContinuation,
        tableMediaWiki,
        script, horizontalLine], endToken)
findMarkup = findMarkup.setPseudoParseAction(pseudoActionFindMarkup)


content << ZeroOrMore(NotAny(endToken) + findMarkup)  # .setResultsName("ZeroOrMore")
content = content.leaveWhitespace().setValidateAction(validateNonEmpty).parseWithTabs()



text = content + stringEnd


# Run optimizer

# Separate element for LanguageHelper.parseTodoEntry()
todoAsWhole = todoAsWhole.optimize(("regexcombine",)).parseWithTabs()

# Whole text, optimizes subelements recursively
text = text.optimize(("regexcombine",)).parseWithTabs()


# print "--content regex", repr(findMarkup.getRegexCombiner().getRegex().pattern)
# text = text.parseWithTabs()


# text.setDebugRecurs(True)
# tableMediaWiki.setDebugRecurs(True, 5)
# content.setDebugRecurs(True, 5)



def _buildBaseDict(wikiDocument=None, formatDetails=None):
    if formatDetails is None:
        if wikiDocument is None:
            formatDetails = WikiDocument.getUserDefaultWikiPageFormatDetails()
            formatDetails.setWikiLanguageDetails(WikiLanguageDetails(None, None))
        else:
            formatDetails = wikiDocument.getWikiDefaultWikiPageFormatDetails()

    return {"wikiFormatDetails": formatDetails
        }



# -------------------- API for plugin WikiParser --------------------
# During beta state of the WikidPad version, this API isn't stable yet, 
# so changes may occur!


class _TheParser(object):
    @staticmethod
    def reset():
        """
        Reset possible internal states of a (non-thread-safe) object for
        later reuse.
        """
        pass

    @staticmethod
    def getWikiLanguageName():
        """
        Return the internal name of the wiki language implemented by this
        parser.
        """
        return WIKI_LANGUAGE_NAME



    @staticmethod
    def _postProcessing(intLanguageName, content, formatDetails, pageAst,
            threadstop):
        """
        Do some cleanup after main parsing.
        Not part of public API.
        """
        autoLinkRelaxRE = None
        if formatDetails.autoLinkMode == u"relax":
            relaxList = formatDetails.wikiDocument.getAutoLinkRelaxInfo()

            def recursAutoLink(ast):
                newAstNodes = []
                for node in ast.getChildren():
                    if isinstance(node, NonTerminalNode):
                        newAstNodes.append(recursAutoLink(node))
                        continue
    
                    if node.name == "plainText":
                        text = node.text
                        start = node.pos
                        
                        threadstop.testValidThread()
                        while text != u"":
                            # The foundWordText is the text as typed in the page
                            # foundWord is the word as entered in database
                            # These two may differ (esp. in whitespaces)
                            foundPos = len(text)
                            foundWord = None
                            foundWordText = None
                            
                            # Search all regexes for the earliest match
                            for regex, word in relaxList:
                                match = regex.search(text)
                                if match:
                                    pos = match.start(0)
                                    if pos < foundPos:
                                        # Match is earlier than previous
                                        foundPos = pos
                                        foundWord = word
                                        foundWordText = match.group(0)
                                        if pos == 0:
                                            # Can't find a better match -> stop loop
                                            break

                            # Add token for text before found word (if any)
                            preText = text[:foundPos]
                            if preText != u"":
                                newAstNodes.append(buildSyntaxNode(preText,
                                        start, "plainText"))
                
                                start += len(preText)
                                text = text[len(preText):]
                            
                            if foundWord is not None:
                                wwNode = buildSyntaxNode(
                                        [buildSyntaxNode(foundWordText, start, "word")],
                                        start, "wikiWord")
                                        
                                wwNode.searchFragment = None
                                wwNode.anchorLink = None
                                wwNode.wikiWord = foundWord
                                wwNode.titleNode = buildSyntaxNode(foundWordText, start, "plainText") # None

                                newAstNodes.append(wwNode)

                                inc = max(len(foundWordText), 1)
                                start += inc
                                text = text[inc:]

                        continue

                    newAstNodes.append(node)


                ast.sub = newAstNodes
    
                return ast

            pageAst = recursAutoLink(pageAst)
        
        return pageAst

    @staticmethod
    def parse(intLanguageName, content, formatDetails, threadstop):
        """
        Parse the  content  written in wiki language  intLanguageName  using
        formatDetails  and regularly call  threadstop.testRunning()  to
        raise exception if execution thread is no longer current parsing
        thread.
        """

        if len(content) == 0:
            return buildSyntaxNode([], 0, "text")

        if formatDetails.noFormat:
            return buildSyntaxNode([buildSyntaxNode(content, 0, "plainText")],
                    0, "text")

        baseDict = _buildBaseDict(formatDetails=formatDetails)

##         _prof.start()
        try:
            t = text.parseString(content, parseAll=True, baseDict=baseDict,
                    threadstop=threadstop)
            t = buildSyntaxNode(t, 0, "text")

            t = _TheParser._postProcessing(intLanguageName, content, formatDetails,
                    t, threadstop)

        finally:
##             _prof.stop()
            pass

        return t

THE_PARSER = _TheParser()





class WikiLanguageDetails(object):
    """
    Stores state of wiki language specific options and allows to check if
    two option sets are equivalent.
    """
    __slots__ = ("__weakref__", "footnotesAsWws", "wikiDocument")

    def __init__(self, wikiDocument, docPage):
        self.wikiDocument = wikiDocument
        if self.wikiDocument is None:
            # Set wiki-independent default values
            self.footnotesAsWws = False
        else:
            self.footnotesAsWws = self.wikiDocument.getWikiConfig().getboolean(
                    "main", "footnotes_as_wikiwords", False)

    @staticmethod
    def getWikiLanguageName():
        return WIKI_LANGUAGE_NAME


    def isEquivTo(self, details):
        """
        Compares with other details object if both are "equivalent"
        """
        return self.getWikiLanguageName() == details.getWikiLanguageName() and \
                self.footnotesAsWws == details.footnotesAsWws


class _WikiLinkPath(object):
    __slots__ = ("upwardCount", "components")
    def __init__(self, link=None, pageName=None, upwardCount=-1,
            components=None):
        assert (link is None) or (pageName is None)

        if pageName is not None:
            # Handle wiki word as absolute link
            self.upwardCount = -1
            self.components = pageName.split(u"/")
            return

        if link is None:
            if components is None:
                components = []

            self.upwardCount = upwardCount
            self.components = components
            return
        
        if link == u".":
            # Link to self
            self.upwardCount = 0
            self.components = []
            return

        if link.startswith(u"//"):
            self.upwardCount = -1
            self.components = link[2:].split(u"/")
            return
        
        if link.startswith(u"/"):
            self.upwardCount = 0
            self.components = link[1:].split(u"/")
            return

        comps = link.split(u"/")

        for i in xrange(0, len(comps)):
            if comps[i] != "..":
                self.upwardCount = i + 1
                self.components = comps[i:]
                return
        
        self.upwardCount = len(comps)
        self.components = []
        
    def clone(self):
        result = _WikiLinkPath()
        result.upwardCount = self.upwardCount
        result.components = self.components[:]
        
        return result

    def __repr__(self):
        return "_WikiLinkPath(upwardCount=%i, components=%s)" % \
                (self.upwardCount, repr(self.components))

    def isAbsolute(self):
        return self.upwardCount == -1
        
    def join(self, otherPath):
        if otherPath.upwardCount == -1:
            self.upwardCount = -1
            self.components = otherPath.components[:]
            return
        elif otherPath.upwardCount == 0:
            self.components = self.components + otherPath.components
        else:
            if otherPath.upwardCount <= len(self.components):
                self.components = self.components[:-otherPath.upwardCount] + \
                        otherPath.components
            else:
                # Going back further than self was deep (eliminating
                # more components than self had)

                if self.upwardCount == -1:
                    # Actually an error (going upward after already reaching root)
                    # TODO: Handle as error?
                    self.components = otherPath.components[:]
                else:
                    # Add up upwardCount of other path after subtracting
                    # number of own components because otherPath walked
                    # over them already
                    self.upwardCount += otherPath.upwardCount - \
                            len(self.components)

                    self.components = otherPath.components[:]


    def getLinkCore(self):
        comps = u"/".join(self.components)
        if self.upwardCount == -1:
            return u"//" + comps
        elif self.upwardCount == 0:
            return u"/" + comps
        elif self.upwardCount == 1:
            return comps
        else:
            return u"/".join([u".."] * (self.upwardCount - 1)) + u"/" + comps


    def resolveWikiWord(self, basePath):
        if self.isAbsolute():
            # Absolute is checked separately so basePath can be None if
            # self is absolute
            return u"/".join(self.components)

        absPath = basePath.joinTo(self)
        return u"/".join(absPath.components)


    def resolvePrefixSilenceAndWikiWordLink(self, basePath):
        """
        If using subpages this is used to resolve a link to the right wiki word
        for autocompletion. It returns a tuple (prefix, silence, pageName).
        Autocompletion now searches for all wiki words starting with pageName. For
        all found items it removes the first  silence  characters, prepends the  prefix
        instead and uses the result as suggestion for autocompletion.
        
        If prefix is None autocompletion is not possible.
        """
        if self.isAbsolute():
            return u"//", 0, self.resolveWikiWord(None)

        assert basePath.isAbsolute()
        
        if len(self.components) == 0:
            # link path only consists of ".." -> autocompletion not possible
            if self.upwardCount == 0:
                return None, None, u"/".join(basePath.components)

            return None, None, u"/".join(basePath.components[:-self.upwardCount])

        if self.upwardCount == 0:
            return u"/", len(basePath.resolveWikiWord(None)) + 1, \
                    u"/".join(basePath.components + self.components)

        def lenAddOne(s):
            return len(s) + 1 if s != "" else 0

        if self.upwardCount == 1:
            return u"", \
                    lenAddOne(u"/".join(basePath.components[:-1])), \
                    u"/".join(basePath.components[:-1] + self.components)

        return u"/".join([u".."] * (self.upwardCount - 1)) + u"/", \
                lenAddOne(u"/".join(basePath.components[:-self.upwardCount])), \
                u"/".join(basePath.components[:-self.upwardCount] +
                self.components)



    def joinTo(self, otherPath):
        result = self.clone()
        result.join(otherPath)
        return result



    @staticmethod
    def isAbsoluteLinkCore(linkCore):
        return linkCore.startswith(u"//")


    @staticmethod
    def getRelativePathByAbsPaths(targetAbsPath, baseAbsPath,
            downwardOnly=True):
        """
        Create a link to targetAbsPath relative to baseAbsPath.
        If downwardOnly is False, the link may contain parts to go to parents
            or siblings
        in path (in this wiki language, ".." are used for this).
        If downwardOnly is True, the function may return None if a relative
        link can't be constructed.
        """
        assert targetAbsPath.isAbsolute() and baseAbsPath.isAbsolute()

        wordPath = targetAbsPath.components[:]
        baseWordPath = baseAbsPath.components[:]
        
        result = _WikiLinkPath()
        
        if downwardOnly:
            if len(baseWordPath) >= len(wordPath):
                return None
            if baseWordPath != wordPath[:len(baseWordPath)]:
                return None
            
            result.upwardCount = 0
            result.components = wordPath[len(baseWordPath):]
            return result
        # TODO test downwardOnly == False
        else:
            # Remove common path elements
            while len(wordPath) > 0 and len(baseWordPath) > 0 and \
                    wordPath[0] == baseWordPath[0]:
                del wordPath[0]
                del baseWordPath[0]
            
            if len(baseWordPath) == 0:
                if len(wordPath) == 0:
                    return None  # word == baseWord, TODO return u"." or something

                result.upwardCount = 0
                result.components = wordPath
                return result

            result.upwardCount = len(baseWordPath)
            result.components = wordPath
            return result
        






_RE_LINE_INDENT = re.compile(ur"^[ \t]*")

class _TheHelper(object):
    @staticmethod
    def reset():
        pass

    @staticmethod
    def getWikiLanguageName():
        return WIKI_LANGUAGE_NAME


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiWord(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki word and no settings
        are against it. The camelCase black list is not checked.
        The function returns None IFF THE WORD IS VALID, an error string
        otherwise
        """
        if settings is not None and settings.has_key("footnotesAsWws"):
            footnotesAsWws = settings["footnotesAsWws"]
        else:
            if wikiDocument is None:
                footnotesAsWws = False
            else:
                footnotesAsWws = wikiDocument.getWikiConfig().getboolean(
                        "main", "footnotes_as_wikiwords", False)

        if not footnotesAsWws and footnoteRE.match(word):
            return _(u"This is a footnote")

        if wikiPageNameRE.match(word):
            return None
        else:
            return _(u"This is syntactically not a wiki word")


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiLink(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki link and no settings
        are against it. The camelCase black list is not checked.
        The function returns None IFF THE WORD IS VALID, an error string
        otherwise
        """
        if settings is not None and settings.has_key("footnotesAsWws"):
            footnotesAsWws = settings["footnotesAsWws"]
        else:
            if wikiDocument is None:
                footnotesAsWws = False
            else:
                footnotesAsWws = wikiDocument.getWikiConfig().getboolean(
                        "main", "footnotes_as_wikiwords", False)

        if not footnotesAsWws and footnoteRE.match(word):
            return _(u"This is a footnote")

        if wikiLinkCoreRE.match(word):
            return None
        else:
            return _(u"This is syntactically not a wiki word")


    @staticmethod
    def extractWikiWordFromLink(word, wikiDocument=None, basePage=None):  # TODO Problems with subpages?
        """
        Strip brackets and other link details if present and return wikiWord
        if a valid wiki word can be extracted, None otherwise.
        """
        if wikiDocument is None and basePage is not None:
            wikiDocument = basePage.getWikiDocument()

        if basePage is None:
            baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        else:
            baseDict = _buildBaseDict(formatDetails=basePage.getFormatDetails())

        try:
            t = extractableWikiWord.parseString(word, parseAll=True,
                    baseDict=baseDict)
            t = t[0]
            return t.wikiWord
        except ParseException:
            return None


    resolveWikiWordLink = staticmethod(resolveWikiWordLink)
    """
    If using subpages this is used to resolve a link to the right wiki word
    relative to basePage on which the link is placed.
    It returns the absolute link (page name).
    """


    @staticmethod
    def resolvePrefixSilenceAndWikiWordLink(link, basePage):
        """
        If using subpages this is used to resolve a link to the right wiki word
        for autocompletion. It returns a tuple (prefix, silence, pageName).
        Autocompletion now searches for all wiki words starting with pageName. For
        all found items it removes the first  silence  characters, prepends the  prefix
        instead and uses the result as suggestion for autocompletion.
        
        If prefix is None autocompletion is not possible.
        """
        linkPath = _WikiLinkPath(link=link)
        if linkPath.isAbsolute():
            return linkPath.resolvePrefixSilenceAndWikiWordLink(None)

        if basePage is None:
            return u"", 0, link  # TODO:  Better reaction?
        
        basePageName = basePage.getWikiWord()
        if basePageName is None:
            return u"", 0, link  # TODO:  Better reaction?
        
        return linkPath.resolvePrefixSilenceAndWikiWordLink(_WikiLinkPath(
                pageName=basePageName))



    @staticmethod
    def parseTodoValue(todoValue, wikiDocument=None):
        """
        Parse a todo value (right of the colon) and return the node or
        return None if value couldn't be parsed
        """
        baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        try:
            t = todoContent.parseString(todoValue, parseAll=True,
                    baseDict=baseDict)
            return t[0]
        except:
            return None


    @staticmethod
    def parseTodoEntry(entry, wikiDocument=None):
        """
        Parse a complete todo entry (without end-token) and return the node or
        return None if value couldn't be parsed
        """
        baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        try:
            t = todoAsWhole.parseString(entry, parseAll=True,
                    baseDict=baseDict)
            return t[0]
        except:
            traceback.print_exc()
            return None


    @staticmethod
    def _createAutoLinkRelaxWordEntryRE(word):
        """
        Get compiled regular expression for one word in autoLink "relax"
        mode.

        Not part of public API.
        """
        # Split into parts of contiguous alphanumeric characters
        parts = AutoLinkRelaxSplitRE.split(word)
        # Filter empty parts
        parts = [p for p in parts if p != u""]

        # Instead of original non-alphanum characters allow arbitrary
        # non-alphanum characters
        pat = ur"\b" + (AutoLinkRelaxJoinPAT.join(parts)) + ur"\b"
        regex = re.compile(pat, AutoLinkRelaxJoinFlags)

        return regex


    @staticmethod
    def buildAutoLinkRelaxInfo(wikiDocument):
        """
        Build some cache info needed to process auto-links in "relax" mode.
        This info will be given back in the formatDetails when calling
        _TheParser.parse().
        The implementation for this plugin creates a list of regular
        expressions and the related wiki words, but this is not mandatory.
        """
        # Build up regular expression
        # First fetch all wiki words
        words = wikiDocument.getWikiData().getAllProducedWikiLinks()

        # Sort longest words first
        words.sort(key=lambda w: len(w), reverse=True)
        
        return [(_TheHelper._createAutoLinkRelaxWordEntryRE(w), w)
                for w in words if w != u""]


    @staticmethod
    def createWikiLinkPathObject(*args, **kwargs):
        return _WikiLinkPath(*args, **kwargs)


    @staticmethod
    def isAbsoluteLinkCore(linkCore):
        return _WikiLinkPath.isAbsoluteLinkCore(linkCore)


    @staticmethod
    def createLinkFromWikiWord(word, wikiPage, forceAbsolute=False):
        """
        Create a link from word which should be put on wikiPage.
        """
        wikiDocument = wikiPage.getWikiDocument()
        
        targetPath = _WikiLinkPath(pageName=word)

        if forceAbsolute:
            return BracketStart + targetPath.getLinkCore() + BracketEnd

        linkCore = _TheHelper.createRelativeLinkFromWikiWord(
                word, wikiPage.getWikiWord(), downwardOnly=False)
                
        if _TheHelper.isCcWikiWord(word) and _TheHelper.isCcWikiWord(linkCore):
            wikiFormatDetails = wikiPage.getFormatDetails()
            if wikiFormatDetails.withCamelCase:
                
                ccBlacklist = wikiDocument.getCcWordBlacklist()
                if not word in ccBlacklist:
                    return linkCore
        
        return BracketStart + linkCore + BracketEnd


    @staticmethod
    def createAbsoluteLinksFromWikiWords(words, wikiPage=None):
        """
        Create particularly stable links from a list of words which should be
        put on wikiPage.
        """
        return u"\n".join([u"%s//%s%s" % (BracketStart, w, BracketEnd)
                for w in words])
                
#     # For compatibility. TODO: Remove
#     createStableLinksFromWikiWords = createAbsoluteLinksFromWikiWords


    @staticmethod
    def createWikiLinkFromText(text, bracketed=True):
        text = text.replace(BracketStart, u"").replace(BracketEnd, u"")
        while text.startswith(u"+"):
            text = text[1:]
        
        text = text.strip()

        if len(text) == 0:
            return u""

        text = text[0:1].upper() + text[1:]
        if bracketed:
            text = BracketStart + text + BracketEnd

        return text


    @staticmethod
    def createRelativeLinkFromWikiWord(word, baseWord, downwardOnly=True):
        """
        Create a link to wikiword word relative to baseWord.
        If downwardOnly is False, the link may contain parts to go to parents
            or siblings
        in path (in this wiki language, ".." are used for this).
        If downwardOnly is True, the function may return None if a relative
        link can't be constructed.
        """
        
        relPath = _WikiLinkPath.getRelativePathByAbsPaths(_WikiLinkPath(
                pageName=word), _WikiLinkPath(pageName=baseWord),
                downwardOnly=downwardOnly)
        
        if relPath is None:
            return None
        
        return relPath.getLinkCore()

    @staticmethod
    def createUrlLinkFromPath(wikiDocument, path, relative=False,
            bracketed=False, protocol=None):
        if bracketed:
            addSafe = ' '
        else:
            addSafe = ''

        if relative:
            url = wikiDocument.makeAbsPathRelUrl(path, addSafe=addSafe)

            if url is None:
                # Relative not possible -> absolute instead
                relative = False
            else:
                if protocol == "wiki":
                    url = u"wiki" + url  # Combines to "wikirel://"

        if not relative:
            if protocol == "wiki":
                url = u"wiki:" + urlFromPathname(path, addSafe=addSafe)
            else:
                url = u"file:" + urlFromPathname(path, addSafe=addSafe)

        if bracketed:
            url = BracketStart + url + BracketEnd
        
        return url


    @staticmethod
    def createAttributeFromComponents(key, value, wikiPage=None):
        """
        Build an attribute from key and value.
        TODO: Check for necessary escaping
        """
        return u"%s%s: %s%s\n" % (BracketStart, key, value, BracketEnd)
        

    @staticmethod
    def isCcWikiWord(word):
        return False


    @staticmethod
    def findNextWordForSpellcheck(text, startPos, wikiPage):
        """
        Find in text next word to spellcheck, beginning at position startPos
        
        Returns tuple (start, end, spWord) which is either (None, None, None)
        if no more word can be found or returns start and after-end of the
        spWord to spellcheck.
        
        TODO: Move away because this is specific to human language,
            not wiki language.
        """
        while True:
            mat = TextWordRE.search(text, startPos)
            if mat is None:
                # No further word
                return (None, None, None)

            if mat.group("negative") is not None:
                startPos = mat.end()
                continue

            start, end = mat.span()
            spWord = mat.group()

            return (start, end, spWord)


    @staticmethod
    def prepareAutoComplete(editor, text, charPos, lineStartCharPos,
            wikiDocument, docPage, settings):
        """
        Called when user wants autocompletion.
        text -- Whole text of page
        charPos -- Cursor position in characters
        lineStartCharPos -- For convenience and speed, position of the 
                start of text line in which cursor is.
        wikiDocument -- wiki document object
        docPage -- DocPage object on which autocompletion is done
        closingBracket -- boolean iff a closing bracket should be suggested
                for bracket wikiwords and attributes

        returns -- a list of tuples (sortKey, entry, backStepChars) where
            sortKey -- unistring to use for sorting entries alphabetically
                using right collator
            entry -- actual unistring entry to show and to insert if
                selected
            backStepChars -- numbers of chars to delete to the left of cursor
                before inserting entry
        """
        line = text[lineStartCharPos:charPos]
        rline = revStr(line)
        backStepMap = {}
        closingBracket = settings.get("closingBracket", False)
        builtinAttribs = settings.get("builtinAttribs", False)

        # TODO Sort entries appropriately (whatever this means)

        wikiData = wikiDocument.getWikiData()
        baseWordSegments = docPage.getWikiWord().split(u"/")

        mat2 = RevWikiWordRE2.match(rline)
        mat3 = RevAttributeValue.match(rline)
        if mat2:
            # may be not-CamelCase word or in an attribute name
            tofind = line[-mat2.end():]

            # Should a closing bracket be appended to suggested words?
            if closingBracket:
                wordBracketEnd = BracketEnd
            else:
                wordBracketEnd = u""
            
            backstep = len(tofind)

            prefix, silence, link = _TheHelper.resolvePrefixSilenceAndWikiWordLink(
                    tofind[len(BracketStart):], docPage)
            
            if prefix is not None:
                for word in wikiData.getWikiPageLinkTermsStartingWith(
                        link, True):
                    backStepMap[BracketStart + prefix + word[silence:] +
                            wordBracketEnd] = backstep

            for prop in wikiDocument.getAttributeNamesStartingWith(
                    tofind[len(BracketStart):], builtinAttribs):
                backStepMap[BracketStart + prop] = backstep
        elif mat3:
            # In an attribute value
            tofind = line[-mat3.end():]
            propkey = revStr(mat3.group(3))
            propfill = revStr(mat3.group(2))
            propvalpart = revStr(mat3.group(1))
            values = filter(lambda pv: pv.startswith(propvalpart),
                    wikiDocument.getDistinctAttributeValuesByKey(propkey,
                    builtinAttribs))

            for v in values:
                backStepMap[BracketStart + propkey +
                        propfill + v + BracketEnd] = len(tofind)

        mat = RevTodoKeyRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            for t in wikiData.getTodos():
                td = t[1]
                if not td.startswith(tofind):
                    continue

#                 tdmat = ToDoREWithCapturing.match(td)
#                 key = tdmat.group(1) + u":"
                key = td + u":"
                backStepMap[key] = len(tofind)

        mat = RevTodoValueRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            combinedTodos = [t[1] + ":" + t[2] for t in wikiData.getTodos()]
#             todos = [t[1] for t in wikiData.getTodos() if t[1].startswith(tofind)]
            todos = [t for t in combinedTodos if t.startswith(tofind)]
            for t in todos:
                backStepMap[t] = len(tofind)

        mat = RevWikiWordAnchorRE2.match(rline)
        if mat:
            # In an anchor of a possible bracketed wiki word
            tofind = line[-mat.end():]
            wikiLinkCore = revStr(mat.group("wikiWord"))
            wikiWord = _TheHelper.resolvePrefixSilenceAndWikiWordLink(
                    wikiLinkCore, docPage)[2]

            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]

                for a in anchors:
                    backStepMap[BracketStart + wikiLinkCore +
                            BracketEnd +
                            WikiWordAnchorStart + a] = len(tofind)
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass

        acresult = backStepMap.keys()
        
        if len(acresult) > 0:
            # formatting.BracketEnd
            acresultTuples = []
            for r in acresult:
                if r.endswith(BracketEnd):
                    rc = r[: -len(BracketEnd)]
                else:
                    rc = r
                acresultTuples.append((rc, r, backStepMap[r]))

            return acresultTuples
        else:
            return []


    @staticmethod
    def handleNewLineBeforeEditor(editor, text, charPos, lineStartCharPos,
            wikiDocument, settings):
        """
        Processes pressing of a newline in editor before editor processes it.
        Returns True iff the actual newline should be processed by
            editor yet.
        """
        # autoIndent, autoBullet, autoUnbullet
        
        line = text[lineStartCharPos:charPos]

        if settings.get("autoUnbullet", False):
            # Check for lonely bullet
            mat = BulletRE.match(line)
            if mat and mat.end(0) == len(line):
                editor.SetSelectionByCharPos(lineStartCharPos, charPos)
                editor.ReplaceSelection( mat.group("indentBullet") +
                mat.group("preLastBullet"))
                return False

        return True


    @staticmethod
    def handleNewLineAfterEditor(editor, text, charPos, lineStartCharPos,
            wikiDocument, settings):
        """
        Processes pressing of a newline after editor processed it (if 
        handleNewLineBeforeEditor returned True).
        """
        currentLine = editor.GetCurrentLine()

        if currentLine > 0:
            previousLine = editor.GetLine(currentLine - 1)
    
            # check if the prev level was a bullet level
            if settings.get("autoBullets", False):
                match = BulletRE.match(previousLine)
                if match:
                    if match.group("lastBullet") == u";":
                        # Special case: Last bullet was definition term
                        # -> replace by definition data
                        editor.AddText( match.group("indentBullet") +
                                match.group("preLastBullet") + u":" +
                                match.group("lastBulletWhite") )
                    else:
                        editor.AddText(match.group(0))
                    return

            indent = _RE_LINE_INDENT.match(previousLine).group(0)
            if settings.get("autoIndent", False):
                editor.AddText(indent)
                return


    @staticmethod
    def handleRewrapText(editor, settings):
        # TODO Handle bullets correctly
        curPos = editor.GetCurrentPos()

        # search back for start of the para
        curLineNum = editor.GetCurrentLine()
        curLine = editor.GetLine(curLineNum)
        while curLineNum > 0:
            # don't wrap previous bullets with this bullet
            if BulletRE.match(curLine):
                break

            if EmptyLineRE.match(curLine):
                curLineNum = curLineNum + 1
                break

            curLineNum = curLineNum - 1
            curLine = editor.GetLine(curLineNum)
        startLine = curLineNum

        # search forward for end of the para
        curLineNum = editor.GetCurrentLine()
        curLine = editor.GetLine(curLineNum)
        while curLineNum <= editor.GetLineCount():
            # don't wrap the next bullet with this bullet
            if curLineNum > startLine:
                if BulletRE.match(curLine):
                    curLineNum = curLineNum - 1
                    break

            if EmptyLineRE.match(curLine):
                curLineNum = curLineNum - 1
                break

            curLineNum = curLineNum + 1
            curLine = editor.GetLine(curLineNum)
        endLine = curLineNum
        
        if (startLine <= endLine):
            # get the start and end of the lines
            startPos = editor.PositionFromLine(startLine)
            endPos = editor.GetLineEndPosition(endLine)

            # get the indentation for rewrapping
            indent = _RE_LINE_INDENT.match(editor.GetLine(startLine)).group(0)
            subIndent = indent

            # if the start of the para is a bullet the subIndent has to change
            if BulletRE.match(editor.GetLine(startLine)):
                subIndent = indent + u"  "

            # get the text that will be wrapped
            indentedStartPos = startPos + editor.bytelenSct(indent)
            text = editor.GetTextRange(indentedStartPos, endPos)
            # remove spaces, newlines, etc
            text = re.sub("[\s\r\n]+", " ", text)

            # wrap the text
            wrapPosition = 70
            try:
                wrapPosition = int(
                        editor.getLoadedDocPage().getAttributeOrGlobal(
                        "wrap", "70"))
            except:
                pass

            # make the min wrapPosition 5
            if wrapPosition < 5:
                wrapPosition = 5

            if editor.isCharWrap():
                lines = []
                for s in xrange(0, len(text), wrapPosition):
                    lines.append(text[s:s+wrapPosition])
                    
                filledText = u"\n".join(lines)
            else:
                filledText = fill(text, width=wrapPosition,
                        initial_indent=indent, 
                        subsequent_indent=subIndent)

            # replace the text based on targetting
            editor.SetTargetStart(startPos)
            editor.SetTargetEnd(endPos)
            editor.ReplaceTarget(filledText)
            editor.GotoPos(endPos)


    @staticmethod 
    def handlePasteRawHtml(editor, rawHtml, settings):
        # Remove possible body end tags
        rawHtml = rawHtml.replace(u"</body>", u"")
        if rawHtml:
            editor.ReplaceSelection(u"<body>" + rawHtml + u"</body>")
            return True

        return False


    @staticmethod
    def getNewDefaultWikiSettingsPage(mainControl):
        """
        Return default text of the "WikiSettings" page for a new wiki.
        """
        return _(u"""++ Wiki Settings

These are your default global settings.

[global.importance.low.color: grey]
[global.importance.high.bold: true]
[global.contact.icon: contact]
[global.wrap: 70]

[icon: cog]
""")  # TODO Localize differently?


    @staticmethod
    def createWikiLanguageDetails(wikiDocument, docPage):
        """
        Returns a new WikiLanguageDetails object based on current configuration
        """
        return WikiLanguageDetails(wikiDocument, docPage)
        
        
    
    _RECURSIVE_STYLING_NODE_NAMES = frozenset(("table", "tableRow", "tableCell",
                        "orderedList", "unorderedList", "indentedText",
                        "noExport"))
                        
    @staticmethod
    def getRecursiveStylingNodeNames():
        """
        Returns a set of those node names of NonTerminalNode-s  for which the
        WikiTxtCtrl.processTokens() should process children recursively.
        """
        return _TheHelper._RECURSIVE_STYLING_NODE_NAMES
        
        
    _FOLDING_NODE_DICT = {
            "tableMediaWiki": (True, False),
            "attribute": (True, False),
            "insertion": (True, False)
        }


    def getFoldingNodeDict(self):
        """
        Retrieve the folding node dictionary which tells
        which AST nodes (other than "heading") should be processed by
        folding.
        The folding node dictionary has the names of the AST node types as keys,
        each value is a tuple (fold, recursive) where
        fold -- True iff node should be folded
        recursive -- True iff node should be processed recursively
        
        The value tuples may contain more than these two items, processFolding()
        must be able to handle that.
        """
        return _TheHelper._FOLDING_NODE_DICT

            


THE_LANGUAGE_HELPER = _TheHelper()



def describeWikiLanguage(ver, app):
    """
    API function for "WikiParser" plugins
    Returns a sequence of tuples describing the supported
    insertion keys. Each tuple has the form (intLanguageName, hrLanguageName,
            parserFactory, parserIsThreadsafe, editHelperFactory,
            editHelperIsThreadsafe)
    Where the items mean:
        intLanguageName -- internal unique name (should be ascii only) to
            identify wiki language processed by parser
        hrLanguageName -- human readable language name, unistring
            (TODO: localization)
        parserFactory -- factory function to create parser object(s) fulfilling

        parserIsThreadsafe -- boolean if parser is threadsafe. If not this
            will currently lead to a very inefficient operation
        processHelperFactory -- factory for helper object containing further
            functions needed for editing, tree presentation and so on.
        editHelperIsThreadsafe -- boolean if edit helper functions are
            threadsafe.

    Parameters:

    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """

    return ((WIKI_LANGUAGE_NAME, WIKI_HR_LANGUAGE_NAME, parserFactory,
             True, languageHelperFactory, True),)




def parserFactory(intLanguageName, debugMode):
    """
    Builds up a parser object. If the parser is threadsafe this function is
    allowed to return the same object multiple times (currently it should do
    so for efficiency).
    For seldom needed parsers it is recommended to put the actual parser
    construction as singleton in this function to reduce startup time of WikidPad.
    For non-threadsafe parsers it is required to create one inside this
    function at each call.

    intLanguageName -- internal unique name (should be ascii only) to
        identify wiki language to process by parser
    """
    # if text.getDebug() != debugMode:
    #     text.setDebugRecurs(debugMode)

    return THE_PARSER


def languageHelperFactory(intLanguageName, debugMode):
    """
    Builds up a language helper object. If the object is threadsafe this function is
    allowed to return the same object multiple times (currently it should do
    so for efficiency).

    intLanguageName -- internal unique name (should be ascii only) to
        identify wiki language to process by helper
    """
    return THE_LANGUAGE_HELPER

