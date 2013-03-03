"""
Processes versions of wiki pages.
"""

import time, zlib, re
from calendar import timegm

from ..rtlibRepl import minidom

import wx

from pwiki.WikiExceptions import *
import Consts

from ..MiscEvent import MiscEventSourceMixin

from ..StringOps import applyBinCompact, getBinCompactForDiff, \
        fileContentToUnicode, BOM_UTF8, formatWxDate

from ..Serialization import serToXmlUnicode, serFromXmlUnicode, serToXmlInt, \
        serFromXmlInt, iterXmlElementFlat

from ..DocPages import AbstractWikiPage



DAMAGED = object()


class VersionEntry(object):
    __slots__ = ("creationTimeStamp", "unifiedBasePageName", "description",
            "versionNumber", "contentDifferencing", "contentEncoding",
            "xmlNode")

    def __init__(self, unifiedBasePageName, description=None,
            contentDifferencing=u"revdiff", contentEncoding = None):

        self.unifiedBasePageName = unifiedBasePageName
        self.creationTimeStamp = time.time()
        self.description = description

        self.versionNumber = 0 # Invalid, numbers start with 1
        # "complete" or reverse differential ("revdiff") content?
        self.contentDifferencing = contentDifferencing
        self.contentEncoding = contentEncoding
        
        self.xmlNode = None


    def getFormattedCreationDate(self, formatStr):
        return formatWxDate(formatStr, wx.DateTimeFromTimeT(
                self.creationTimeStamp))


    def serializeOverviewToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all overview information (not content)
        about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement(u"versionOverviewEntry")

        self.serializeOverviewToXml(xmlNode, xmlDoc)
        
        return xmlNode


    def serializeOverviewToXml(self, xmlNode, xmlDoc):
        """
        Create XML node to contain all overview information (not content)
        about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, u"creationTime", unicode(time.strftime(
                "%Y-%m-%d/%H:%M:%S", time.gmtime(self.creationTimeStamp))),
                replace=True)

        if self.description is not None:
            serToXmlUnicode(xmlNode, xmlDoc, u"description", self.description,
                    replace=True)

        serToXmlInt(xmlNode, xmlDoc, u"versionNumber", self.versionNumber,
                replace=True)
        
        serToXmlUnicode(xmlNode, xmlDoc, u"contentDifferencing",
                self.contentDifferencing, replace=True)
        
        if self.contentEncoding is not None:
            serToXmlUnicode(xmlNode, xmlDoc, u"contentEncoding",
                    self.contentEncoding, replace=True)



    def serializeOverviewFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        self.xmlNode = xmlNode

        timeStr = serFromXmlUnicode(xmlNode, u"creationTime")

        self.creationTimeStamp = timegm(time.strptime(timeStr,
                "%Y-%m-%d/%H:%M:%S"))

        self.description = serFromXmlUnicode(xmlNode, u"description", None)

        self.versionNumber = serFromXmlInt(xmlNode, u"versionNumber")

        self.contentDifferencing = serFromXmlUnicode(xmlNode,
                u"contentDifferencing", u"complete")

        self.contentEncoding = serFromXmlUnicode(xmlNode, u"contentEncoding", None)


    def getUnifiedPageName(self):
        return u"versioning/packet/versionNo/%s/%s" % (self.versionNumber,
                unifiedPageName)



class VersionOverview(MiscEventSourceMixin):
    def __init__(self, wikiDocument, basePage=None, unifiedBasePageName=None):
        MiscEventSourceMixin.__init__(self)

        self.wikiDocument = wikiDocument
        self.basePage = basePage
        if basePage is not None:
            self.unifiedBasePageName = self.basePage.getUnifiedPageName()
        else:
            self.unifiedBasePageName = unifiedBasePageName
        self.versionEntries = []
        self.maxVersionNumber = 0
        
        self.xmlNode = None


    def getUnifiedName(self):
        return u"versioning/overview/" + self.unifiedBasePageName


    def isNotInDatabase(self):
        """
        Can be called before readOverview() to check if the version overview
        is already in database.
        """
        return self.wikiDocument.retrieveDataBlock(self.getUnifiedName()) is None



    def readOverviewFromBytes(self, content):
        """
        Read overview from bytestring content. Needed to handle multi-page text
        imports.
        """
        if content is None:
            self.versionEntries = []
            self.maxVersionNumber = 0
            self.xmlNode = None
            return

        xmlDoc = minidom.parseString(content)
        xmlNode = xmlDoc.firstChild
        self.serializeFromXml(xmlNode)



    def readOverview(self):
        """
        Read and decode overview from database. Most functions can be called
        only after this was called (exception: isNotInDatabase())
        """
        unifName = u"versioning/overview/" + self.unifiedBasePageName

        content = self.wikiDocument.retrieveDataBlock(unifName, default=DAMAGED)
        if content is DAMAGED:
            raise VersioningException(_(u"Versioning data damaged"))

        self.readOverviewFromBytes(content)

        self.fireMiscEventKeys(("reread version overview",
                "changed version overview"))


#         elif content is None:
#             self.versionEntries = []
#             self.maxVersionNumber = 0
#             self.xmlNode = None
#             return
# 
#         xmlDoc = minidom.parseString(content)
#         xmlNode = xmlDoc.firstChild
#         self.serializeFromXml(xmlNode)


    def getDependentDataBlocks(self, omitSelf=False):
        assert not self.isInvalid()

        unifiedPageName = self.unifiedBasePageName

        if omitSelf:
            result = []
        else:
            result = [u"versioning/overview/" + unifiedPageName]

        for entry in self.versionEntries:
            result.append(u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                unifiedPageName))

        return result


    def renameTo(self, newUnifiedPageName):
        """
        Rename all data to newUnifiedPageName. This object becomes invalid after
        doing so, so you must retrieve a new overview for the new name.
        """
        oldUnifiedPageName = self.unifiedBasePageName

        # First copy to new 
        for entry in self.versionEntries:
            oldUnifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                oldUnifiedPageName)
            newUnifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                newUnifiedPageName)

            content = self.wikiDocument.retrieveDataBlock(oldUnifName,
                    default=None)
            if content is None:
                continue
#                 raise VersioningException(_(u"Versioning data damaged"))

            self.wikiDocument.storeDataBlock(newUnifName, content,
                    storeHint=self.getStorageHint())

        self.writeOverview(newUnifiedPageName)

        # Then delete old data
        for entry in self.versionEntries:
            oldUnifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                oldUnifiedPageName)

            self.wikiDocument.deleteDataBlock(oldUnifName)

        oldUnifName = u"versioning/overview/" + oldUnifiedPageName
        self.wikiDocument.deleteDataBlock(oldUnifName)
        
        self.invalidate()
        self.fireMiscEventKeys(("renamed version overview",
                "invalidated version overview"))


    def delete(self):
        """
        Delete all versioning data. This object becomes invalid after
        doing so.
        """
        for entry in self.versionEntries:
            unifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                self.unifiedBasePageName)

            self.wikiDocument.deleteDataBlock(unifName)

        unifName = u"versioning/overview/" + self.unifiedBasePageName
        self.wikiDocument.deleteDataBlock(unifName)

        self.invalidate()
        self.fireMiscEventKeys(("deleted version overview",
                "invalidated version overview"))

    @staticmethod
    def deleteBrokenDataForDocPage(docPage):
        """
        Delete all versioning data of unifPageName in case of broken
        versioning data. This may fail.
        It mainly creates a list of all data blocks which belong to versioning
        data of the given docPage and deletes the blocks.
        """
        unifPageName = docPage.getUnifiedPageName()
        wikiDocument = docPage.getWikiDocument()

        matOb = re.compile(u"^versioning/packet/versionNo/[0-9]+/%s$" %
                re.escape(unifPageName))
        
        dataBlocks = wikiDocument.getDataBlockUnifNamesStartingWith(
                u"versioning/packet/versionNo/")
        
        dataBlocks = [db for db in dataBlocks if matOb.match(db)]
        dataBlocks.append(u"versioning/overview/" + unifPageName)

        for db in dataBlocks:
            wikiDocument.deleteDataBlock(db)


    def writeOverview(self, unifPageName=None):
        if unifPageName is None:
            unifName = u"versioning/overview/" + self.unifiedBasePageName
        else:
            unifName = u"versioning/overview/" + unifPageName

        if len(self.versionEntries) == 0:
            self.wikiDocument.deleteDataBlock(unifName)
            return

        xmlDoc = minidom.getDOMImplementation().createDocument(None, None, None)
        xmlNode = self.serializeToXmlProd(xmlDoc)

        xmlDoc.appendChild(xmlNode)
        content = xmlDoc.toxml("utf-8")

        self.wikiDocument.storeDataBlock(unifName, content,
                storeHint=self.getStorageHint())


    def invalidate(self):
        if self.basePage is not None:
            # Inform base page about invalidation
            self.basePage.releaseVersionOverview()

        self.basePage = None
        self.wikiDocument = None
        self.versionEntries = []


    def isInvalid(self):
        return self.wikiDocument is None

    def getVersionEntries(self):
        return self.versionEntries

    def getStorageHint(self):
        """
        Return appropriate storage hint according to option settings.
        """
        if self.wikiDocument.getWikiConfig().getint("main",
                "versioning_storageLocation", 0) != 1:
            return Consts.DATABLOCK_STOREHINT_INTERN
        else:
            return Consts.DATABLOCK_STOREHINT_EXTERN


    @staticmethod
    def decodeContent(encContent, encoding):
        if encoding is None:
            return encContent
        if encoding == "zlib":
            return zlib.decompress(encContent)

    @staticmethod
    def encodeContent(content, encoding):
        if encoding is None:
            return content
        if encoding == "zlib":
            return zlib.compress(content)


    def serializeToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all information about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement(u"versionOverview")

        self.serializeToXml(xmlNode, xmlDoc)
        
        return xmlNode


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        xmlNode.setAttribute(u"formatVersion", u"0")
        xmlNode.setAttribute(u"readCompatVersion", u"0")
        xmlNode.setAttribute(u"writeCompatVersion", u"0")

        for xmlEntry in iterXmlElementFlat(xmlNode, u"versionOverviewEntry"):
            xmlNode.removeChild(xmlEntry)

        for entry in self.versionEntries:
            entryNode = entry.serializeOverviewToXmlProd(xmlDoc)
            xmlNode.appendChild(entryNode)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode.
        """
        formatVer = int(xmlNode.getAttribute(u"writeCompatVersion"))
        if formatVer > 0:
            SerializationException("Wrong version no. %s for version overview" %
                    formatVer)

        self.xmlNode = xmlNode
        
        versionEntries = []
        maxVersionNumber = 0

        for xmlEntry in iterXmlElementFlat(xmlNode, u"versionOverviewEntry"):
            entry = VersionEntry(self.unifiedBasePageName)
            entry.serializeOverviewFromXml(xmlEntry)
            
            versionEntries.append(entry)
            maxVersionNumber = max(maxVersionNumber, entry.versionNumber)

        self.versionEntries = versionEntries
        self.maxVersionNumber = maxVersionNumber


    def getVersionContentRaw(self, versionNumber):
        if len(self.versionEntries) == 0:
            raise InternalError(u"Tried to retrieve non-existing "
                    u"version number %s from empty list." % versionNumber)

        if versionNumber == -1:
            versionNumber = self.versionEntries[-1].versionNumber

        base = None
        workList = []
        for i in xrange(len(self.versionEntries) - 1, -1, -1):
            entry = self.versionEntries[i]
            if entry.contentDifferencing == u"complete":
                workList = []
                base = entry
            else:
                workList.append(entry)

            if entry.versionNumber == versionNumber:
                break
        else:
            raise InternalError(u"Tried to retrieve non-existing "
                    u"version number %s." % versionNumber)

        if base is None:
            raise InternalError(u"No base version found for getVersionContent(%s)" %
                    versionNumber)

        unifName = u"versioning/packet/versionNo/%s/%s" % (base.versionNumber,
                self.unifiedBasePageName)

        content = self.wikiDocument.retrieveDataBlock(unifName, default=DAMAGED)
        if content is DAMAGED:
            raise VersioningException(_(u"Versioning data damaged"))
        elif content is None:
            raise InternalError(u"Tried to retrieve non-existing "
                    u"packet for version number %s" % versionNumber)

        content = self.decodeContent(content, entry.contentEncoding)

        for entry in workList:
            unifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                    self.unifiedBasePageName)
            packet = self.wikiDocument.retrieveDataBlock(unifName, default=None)
            if content is DAMAGED:
                raise VersioningException(_(u"Versioning data damaged"))
            elif content is None:
                raise InternalError(u"Tried to retrieve non-existing "
                        u"packet for version number %s" % versionNumber)


            content = applyBinCompact(content, packet)

        return content


    def getVersionContent(self, versionNumber):
        return fileContentToUnicode(self.getVersionContentRaw(versionNumber))


    def addVersion(self, content, entry):
        """
        entry.versionNumber is assumed invalid and will be filled by this function.
        """
        if isinstance(content, unicode):
            content = BOM_UTF8 + content.encode("utf-8")
        assert isinstance(content, str)

        completeStep = max(self.wikiDocument.getWikiConfig().getint("main",
                "versioning_completeSteps", 10), 0)

        if completeStep == 0:
            asRevDiff = True
        else:
            if len(self.versionEntries) < completeStep:
                asRevDiff = True
            else:
                asRevDiff = False
                for e in reversed(self.versionEntries[-completeStep:-1]):
                    if e.contentDifferencing == "complete":
                        asRevDiff = True
                        break

        self.maxVersionNumber += 1
        newHeadVerNo = self.maxVersionNumber

        newHeadUnifName = u"versioning/packet/versionNo/%s/%s" % \
                (newHeadVerNo, self.unifiedBasePageName)

        self.wikiDocument.storeDataBlock(newHeadUnifName, content,
                storeHint=self.getStorageHint())

        entry.versionNumber = newHeadVerNo
        entry.unifiedBasePageName = self.unifiedBasePageName
        entry.contentDifferencing = "complete"
        entry.contentEncoding = None
        self.versionEntries.append(entry)

        if len(self.versionEntries) > 1:
            if asRevDiff:
                prevHeadEntry = self.versionEntries[-2]
                prevHeadContent = self.getVersionContentRaw(prevHeadEntry.versionNumber)

                unifName = u"versioning/packet/versionNo/%s/%s" % (prevHeadEntry.versionNumber,
                        self.unifiedBasePageName)
                diffPacket = getBinCompactForDiff(content, prevHeadContent)

                if len(diffPacket) < len(prevHeadContent):
                    prevHeadEntry.contentDifferencing = "revdiff"
                    prevHeadEntry.contentEncoding = None
                    self.wikiDocument.storeDataBlock(unifName, diffPacket,
                            storeHint=self.getStorageHint())

        self.fireMiscEventKeys(("appended version", "changed version overview"))


    def deleteVersion(self, versionNumber):
        if len(self.versionEntries) == 0:
            raise InternalError("Non-existing version %s to delete (empty list)." %
                    versionNumber)

        if versionNumber == -1:
            versionNumber = self.versionEntries[-1].versionNumber

        if versionNumber == self.versionEntries[0].versionNumber:
            # Delete oldest
            unifName = u"versioning/packet/versionNo/%s/%s" % (versionNumber,
                    self.unifiedBasePageName)

            self.wikiDocument.deleteDataBlock(unifName)
            del self.versionEntries[0]
            self.fireMiscEventKeys(("deleted version", "changed version overview"))

            return

        if versionNumber == self.versionEntries[-1].versionNumber:
            # Delete newest

            # We can assume here that len(self.versionEntries) >= 2 otherwise
            # previous "if" would have been true.

            prevHeadEntry = self.versionEntries[-2]
            newContent = self.getVersionContentRaw(prevHeadEntry.versionNumber)
            
            unifName = u"versioning/packet/versionNo/%s/%s" % (prevHeadEntry.versionNumber,
                    self.unifiedBasePageName)
            prevHeadEntry.contentDifferencing = "complete"
            self.wikiDocument.storeDataBlock(unifName, newContent,
                    storeHint=self.getStorageHint())
                
            unifName = u"versioning/packet/versionNo/%s/%s" % (versionNumber,
                    self.unifiedBasePageName)
            self.wikiDocument.deleteDataBlock(unifName)
            del self.versionEntries[-1]
            self.fireMiscEventKeys(("deleted version", "changed version overview"))

            return

        # Delete some version in-between: Not supported yet.
        raise InternalError("In-between version %s to delete." %
                        versionNumber)



class WikiPageSnapshot(AbstractWikiPage):
    def __init__(self, wikiDocument, baseWikiPage, versionNo):
        AbstractWikiPage.__init__(self, wikiDocument, baseWikiPage.getWikiWord())
        
        self.baseWikiPage = baseWikiPage
        self.versionNumber = versionNo
        
        self.content = self.baseWikiPage.getVersionOverview().getVersionContent(
                versionNo)


#     def setVersionNumber(self, vn):
#         self.versionNumber = vn
#         
#         if vn == 0:
#             content = u""
#         else:
#             content = self.baseWikiPage.getVersionOverview().getVersionContent(vn)
# 
#         self.setEditorText(content)


    def getSnapshotBaseDocPage(self):
        return self.baseWikiPage
        
    def getSnapshotVersionNumber(self):
        return self.versionNumber


    def getContent(self):
        return self.content


    def getUnifiedPageName(self):
        if self.versionNumber == 0:
            return None
        
        return u"versioning/version/versionNo/%s/%s" % (self.versionNumber,
                self.baseWikiPage.getWikiWord())


    def isReadOnlyEffect(self):
        """
        Return true if page is effectively read-only, this means
        "for any reason", regardless if error or intention.
        """
        return True


    def getVersionOverview(self):
        return self.baseWikiPage.getVersionOverview()

    def getExistingVersionOverview(self):
        return self.baseWikiPage.getExistingVersionOverview()

    def setPresentation(self, data, startPos):
        """
        Set (a part of) the presentation tuple. This is silently ignored
        if the "write access failed" or "read access failed" flags are
        set in the wiki document.
        data -- tuple with new presentation data
        startPos -- start position in the presentation tuple which should be
                overwritten with data.
        """
        pass  # TODO?
