import string

htmlEntityStrings = {
        ur'==>' : '&rArr;',
        ur'-->' : '&rarr;',
        ur'<==' : '&lArr;',
        ur'<--' : '&larr;',
        }

#regHtmlEntityStrings = ur"\s(" + string.join(htmlEntityStrings.keys(),'|') + ur")\s"
regHtmlEntityStrings = ur"(" + string.join(htmlEntityStrings.keys(),'|') + ur")"
