#===============================================================================
# Copyright 2010 Matt Chaput
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#===============================================================================

"""
This module contains plugins for the query parser. Most of the functionality
of the default query parser is actually provided by plugins.
"""

import re

from whoosh.qparser.syntax import *
from whoosh.qparser.common import get_single_text, rcompile, QueryParserError


class Plugin(object):
    """Base class for parser plugins.
    """
            
    def tokens(self, parser):
        """Returns a list of ``(token_class, priority)`` tuples to add to the
        syntax the parser understands.
        """
        
        return ()
    
    def filters(self, parser):
        """Returns a list of ``(filter_function, priority)`` tuples to add to
        parser.
        """
        
        return ()
    

class RangePlugin(Plugin):
    """Adds the ability to specify term ranges.
    
    This plugin has no configuration.
    
    This plugin is included in the default parser configuration.
    """
    
    def tokens(self, parser):
        return ((RangePlugin.Range, 1), )
    
    class Range(Token):
        expr = rcompile(r"""
        (?P<open>\{|\[)               # Open paren
        
        (                             # Begin optional "start"
          (                           # Begin choice between start1 and start2
            ('(?P<start2>[^']+)')     # Quoted start
            | (?P<start1>[^ ]+)       # ...or regular start
          )                           # End choice
        [ ]+)?                        # Space at end of optional "start"
        
        [Tt][Oo]                      # "to" between start and end
        
        ([ ]+                         # Space at start of optional "end"
          (                           # Begin choice between end1 and end2
            ('(?P<end2>[^']+)')       # Quoted end
            | (?P<end1>[^\]\}]*)      # ...or normal end
          )                           # End choice
        )?                            # End of optional "end
        
        (?P<close>\}|\])              # Close paren
        """, re.VERBOSE)
        
        def __init__(self, start, end, startexcl, endexcl, fieldname=None, boost=1.0):
            self.fieldname = fieldname
            self.start = start
            self.end = end
            self.startexcl = startexcl
            self.endexcl = endexcl
            self.boost = boost
        
        def set_boost(self, b):
            return self.__class__(self.start, self.end, self.startexcl,
                                  self.endexcl, fieldname=self.fieldname,
                                  boost=b)
        
        def set_fieldname(self, name, force=False):
            if force or self.fieldname is None:
                return self.__class__(self.start, self.end, self.startexcl,
                                      self.endexcl, fieldname=name,
                                      boost=self.boost)
            else:
                return self
        
        def __repr__(self):
            r = "%s:(%r, %r, %s, %s)" % (self.fieldname, self.start, self.end,
                                         self.startexcl, self.endexcl)
            if self.boost != 1.0:
                r += "^%s" % self.boost
            return r
        
        @classmethod
        def create(cls, parser, match):
            start = match.group("start2") or match.group("start1")
            end = match.group("end2") or match.group("end1")
            return cls(start, end, startexcl=match.group("open") == "{",
                       endexcl=match.group("close") == "}")
            
        def query(self, parser):
            fieldname = self.fieldname or parser.fieldname
            start, end = self.start, self.end
            if parser.schema and fieldname in parser.schema:
                field = parser.schema[fieldname]
                
                if field.self_parsing():
                    try:
                        rangeq = field.parse_range(fieldname, start, end,
                                                   self.startexcl, self.endexcl,
                                                   boost=self.boost)
                        if rangeq is not None:
                            return rangeq
                    except QueryParserError, e:
                        return query.NullQuery
                
                if start:
                    start = get_single_text(field, start, tokenize=False,
                                            removestops=False)
                if end:
                    end = get_single_text(field, end, tokenize=False,
                                          removestops=False)
            
            if start is None:
                start = u''
            if end is None:
                end = u'\uFFFF'
            
            return query.TermRange(fieldname, start, end, self.startexcl,
                                   self.endexcl, boost=self.boost)
            

class PhrasePlugin(Plugin):
    """Adds the ability to specify phrase queries inside double quotes.
    
    This plugin has no configuration.
    
    This plugin is included in the default parser configuration.
    """
    
    def tokens(self, parser):
        return ((PhrasePlugin.Quotes, 0), )
    
    class Quotes(BasicSyntax):
        expr = rcompile('"(.*?)"')
        
        def __init__(self, text, fieldname=None, boost=1.0, slop=1):
            super(PhrasePlugin.Quotes, self).__init__(text, fieldname=fieldname,
                                                      boost=boost)
            self.slop = slop
        
        def __repr__(self):
            r = "%s:q(%r)" % (self.fieldname, self.text)
            if self.boost != 1.0:
                r += "^%s" % self.boost
            return r
        
        @classmethod
        def create(cls, parser, match):
            slop = 1
            #if match.group(5):
            #    try:
            #        slop = int(match.group(5))
            #    except ValueError:
            #        pass
            return cls(match.group(1), slop=slop)
        
        def query(self, parser):
            fieldname = self.fieldname or parser.fieldname
            if parser.schema and fieldname in parser.schema:
                field = parser.schema[fieldname]
                #if field.self_parsing():
                #    return field.parse_query(fieldname, self.text, boost=self.boost)
                #else:
                words = list(field.process_text(self.text, mode="query")) 
            else:
                words = self.text.split(" ")
            
            return parser.phraseclass(fieldname, words, boost=self.boost,
                                      slop=self.slop)


class SingleQuotesPlugin(Plugin):
    """Adds the ability to specify single "terms" containing spaces by
    enclosing them in single quotes.
    
    This plugin has no configuration.
    
    This plugin is included in the default parser configuration.
    """
     
    def tokens(self, parser):
        return ((SingleQuotesPlugin.SingleQuotes, 0), )
    
    class SingleQuotes(Token):
        expr = rcompile(r"(^|(?<=\W))'(.*?)'(?=\s|\]|[)}]|$)")
        
        @classmethod
        def create(cls, parser, match):
            return Word(match.group(2))


class PrefixPlugin(Plugin):
    """Adds the ability to specify prefix queries by ending a term with an
    asterisk. This plugin is useful if you want the user to be able to create
    prefix but not wildcard queries (for performance reasons). If you are
    including the wildcard plugin, you should not include this plugin as well.
    """
    
    def tokens(self, parser):
        return ((PrefixPlugin.Prefix, 0), )
    
    class Prefix(BasicSyntax):
        expr = rcompile("[^ \t\r\n*]+\\*(?= |$|\\))")
        qclass = query.Prefix
        
        def __repr__(self):
            r = "%s:pre(%r)" % (self.fieldname, self.text)
            if self.boost != 1.0:
                r += "^%s" % self.boost
            return r
        
        @classmethod
        def create(cls, parser, match):
            return cls(match.group(0)[:-1])
        

class WildcardPlugin(Plugin):
    """Adds the ability to specify wildcard queries by using asterisk and
    question mark characters in terms. Note that these types can be very
    performance and memory intensive. You may consider not including this
    type of query.
    
    This plugin is included in the default parser configuration.
    """
    
    def tokens(self, parser):
        return ((WildcardPlugin.Wild, 1), )
    
    class Wild(BasicSyntax):
        # \u055E = Armenian question mark
        # \u061F = Arabic question mark
        # \u1367 = Ethiopic question mark
        expr = rcompile(u"[^ \t\r\n*?\u055E\u061F\u1367]*[*?\u055E\u061F\u1367]\\S*")
        qclass = query.Wildcard
        
        def __repr__(self):
            r = "%s:wild(%r)" % (self.fieldname, self.text)
            if self.boost != 1.0:
                r += "^%s" % self.boost
            return r
        
        @classmethod
        def create(cls, parser, match):
            return cls(match.group(0))
        

class WhitespacePlugin(Plugin):
    """Parses whitespace between words in the query string. You should always
    include this plugin.
    
    This plugin is always automatically included by the QueryParser.
    """
    
    def __init__(self, tokenclass=White):
        self.tokenclass = tokenclass
    
    def tokens(self, parser):
        return ((self.tokenclass, 100), )
    
    def filters(self, parser):
        return ((self.do_whitespace, 500), )
    
    def do_whitespace(self, parser, stream):
        newstream = stream.empty()
        for t in stream:
            if isinstance(t, Group):
                newstream.append(self.do_whitespace(parser, t))
            elif not isinstance(t, self.tokenclass):
                newstream.append(t)
        return newstream


class GroupPlugin(Plugin):
    """Adds the ability to group clauses using parentheses.
    
    This plugin is included in the default parser configuration.
    """
    
    def tokens(self, parser):
        return ((GroupPlugin.Open, 0), (GroupPlugin.Close, 0))
    
    def filters(self, parser):
        # This should basically be the first plugin to run
        return ((GroupPlugin.do_groups, 0), )
    
    @staticmethod
    def do_groups(parser, stream):
        stack = [parser.group()]
        for t in stream:
            if isinstance(t, GroupPlugin.Open):
                stack.append(parser.group())
            elif isinstance(t, GroupPlugin.Close):
                if len(stack) > 1:
                    last = stack.pop()
                    stack[-1].append(last)
            else:
                stack[-1].append(t)
        
        top = stack[0]
        if len(stack) > 1:
            for ls in stack[1:]:
                top.extend(ls)
        
        if len(top) == 1 and isinstance(top[0], Group):
            top = top[0].set_boost(top.boost)
        
        return top
    
    class Open(Singleton):
        expr = rcompile("\\(")
        
    class Close(Singleton):
        expr = rcompile("\\)")


class FieldsPlugin(Plugin):
    """Adds the ability to specify the field of a clause using a colon.
    
    This plugin is included in the default parser configuration.
    """
    
    def tokens(self, parser):
        return ((FieldsPlugin.Field, 0), )
    
    def filters(self, parser):
        return ((FieldsPlugin.do_fieldnames, 100), )

    @staticmethod
    def do_fieldnames(parser, stream):
        newstream = stream.empty()
        newname = None
        for i, t in enumerate(stream):
            if isinstance(t, FieldsPlugin.Field):
                valid = False
                if i < len(stream) - 1:
                    next = stream[i+1]
                    if not isinstance(next, (White, FieldsPlugin.Field)):
                        newname = t.fieldname
                        valid = True
                if not valid:
                    newstream.append(Word(t.fieldname, fieldname=parser.fieldname))
                continue
            
            if isinstance(t, Group):
                t = FieldsPlugin.do_fieldnames(parser, t)
                
            if newname is not None:
                t = t.set_fieldname(newname)
            newstream.append(t)
            newname = None
        
        return newstream
    
    class Field(Token):
        expr = rcompile(u"(\w[\w\d]*):")
        
        def __init__(self, fieldname):
            self.fieldname = fieldname
        
        def __repr__(self):
            return "<%s:>" % self.fieldname
        
        def set_fieldname(self, fieldname, force=False):
            return self.__class__(fieldname)
        
        @classmethod
        def create(cls, parser, match):
            fieldname = match.group(1)
            if not parser.schema or fieldname == "*" or (fieldname in parser.schema):
                return cls(fieldname)
    

class OperatorsPlugin(Plugin):
    """By default, adds the AND, OR, ANDNOT, ANDMAYBE, and NOT operators to
    the parser syntax. This plugin scans the token stream for subclasses of
    :class:`Operator` and calls their :meth:`Operator.make_group` methods
    to allow them to manipulate the stream.
    
    There are two levels of configuration available.
    
    The first level is to change the regular expressions of the default
    operators, using the ``And``, ``Or``, ``AndNot``, ``AndMaybe``, and/or
    ``Not`` keyword arguments. The keyword value can be a pattern string or
    a compiled expression, or None to remove the operator::
    
        qp = qparser.QueryParser("content")
        cp = qparser.OperatorsPlugin(And="&", Or="\\|", AndNot="&!", AndMaybe="&~", Not=None)
        qp.replace_plugin(cp)
    
    You can also specify a list of ``(Operator, priority)`` pairs as the first
    argument to the initializer. For example, assume you have created an
    :class:`InfixOperator` subclass to implement a "before" operator. To add
    this to the operators plugin with a priority of -5, you would do this::
    
        additional = [(MyBefore(), -5)]
        cp = qparser.OperatorsPlugin(additional)
    
    Not that the list of operators you specify with the first argument is IN
    ADDITION TO the defaults. To turn off one of the default operators, you
    can pass None to the corresponding keyword argument::
        
        cp = qparser.OperatorsPlugin([(MyAnd(), 0)], And=None)
        
    If you want ONLY your list operators and none of the default operators, use
    the ``clean`` keyword argument::
    
        cp = qparser.OperatorsPlugin([(MyAnd(), 0)], clean=True)
                                     
    This class replaces the ``CompoundsPlugin``. ``qparser.CompoundsPlugin`` is
    now an alias for this class.
    """
    
    def __init__(self, ops=None, And=r"\sAND\s", Or=r"\sOR\s",
                 AndNot=r"\sANDNOT\s", AndMaybe=r"\sANDMAYBE\s",
                 Not=r"(^|(?<= ))NOT\s", Require=r"(^|(?<= ))REQUIRE\s",
                 clean=False):
        if isinstance(ops, tuple):
            ops = list(ops)
        if not ops:
            ops = []
        
        if not clean:
            if Not: ops.append((PrefixOperator(Not, NotGroup), 0))
            if And: ops.append((InfixOperator(And, AndGroup), 0))
            if Or: ops.append((InfixOperator(Or, OrGroup), 0))
            if AndNot: ops.append((InfixOperator(AndNot, AndNotGroup), -5))
            if AndMaybe: ops.append((InfixOperator(AndMaybe, AndMaybeGroup), -5))
            if Require: ops.append((InfixOperator(Require, RequireGroup), 0))
        
        self.ops = ops
    
    def tokens(self, parser):
        return self.ops
    
    def filters(self, parser):
        return ((self.do_operators, 600), )
    
    def do_operators(self, parser, stream, level=0):
        for op, _ in self.ops:
            if op.left_assoc:
                i = 0
                while i < len(stream):
                    t = stream[i]
                    if t is op:
                        i = t.make_group(parser, stream, i)
                    else:
                        i += 1
            else:
                i = len(stream) - 1
                while i >= 0:
                    t = stream[i]
                    if t is op:
                        i = t.make_group(parser, stream, i)
                    i -= 1
        
        #print " " * level, ">stream=", stream
        newstream = stream.empty()
        for t in stream:
            if isinstance(t, Group):
                t = self.do_operators(parser, t, level+1)
            newstream.append(t)
        
        #print " " * level, "<stream=", newstream
        return newstream

CompoundsPlugin = OperatorsPlugin


class NotPlugin(Plugin):
    """This plugin is deprecated, its functionality is now provided by the
    :class:`OperatorsPlugin`.
    """
    
    def __init__(self, token="(^|(?<= ))NOT "):
        class Not(Singleton):
            expr = rcompile(token)
        
        self.Not = Not
    
    def tokens(self, parser):
        return ((self.Not, 0), )
    
    def filters(self, parser):
        return ((self.do_not, 800), )
    
    def do_not(self, parser, stream):
        newstream = stream.empty()
        notnext = False
        for t in stream:
            if isinstance(t, self.Not):
                notnext = True
                continue
            
            if isinstance(t, Group):
                t = self.do_not(parser, t)
            
            if notnext:
                t = NotGroup([t])
            
            newstream.append(t)
            notnext = False
            
        return newstream
 


class BoostPlugin(Plugin):
    """Adds the ability to boost clauses of the query using the circumflex.
    
    This plugin is included in the default parser configuration.
    """
    
    def tokens(self, parser):
        return ((BoostPlugin.Boost, 0), )
    
    def filters(self, parser):
        return ((BoostPlugin.clean_boost, 0), (BoostPlugin.do_boost, 700))

    @staticmethod
    def clean_boost(parser, stream):
        newstream = stream.empty()
        for i, t in enumerate(stream):
            if isinstance(t, BoostPlugin.Boost):
                if i == 0 or isinstance(stream[i-1], (BoostPlugin.Boost, White)):
                    t = Word(t.original)
            newstream.append(t)
        return newstream

    @staticmethod
    def do_boost(parser, stream):
        newstream = stream.empty()
        
        for t in stream:
            if isinstance(t, Group):
                newstream.append(BoostPlugin.do_boost(parser, t))
                
            elif isinstance(t, BoostPlugin.Boost):
                if newstream:
                    newstream.append(newstream.pop().set_boost(t.boost))
                
            else:
                newstream.append(t)
        
        return newstream
    
    class Boost(Token):
        expr = rcompile("\\^([0-9]+(.[0-9]+)?)($|(?=[ \t\r\n]))")
        
        def __init__(self, original, boost):
            self.original = original
            self.boost = boost
        
        def __repr__(self):
            return "<^%s>" % self.boost
        
        @classmethod
        def create(cls, parser, match):
            try:
                return cls(match.group(0), float(match.group(1)))
            except ValueError:
                return Word(match.group(0))
    

class PlusMinusPlugin(Plugin):
    """Adds the ability to use + and - in a flat OR query to specify required
    and prohibited terms.
    
    This is the basis for the parser configuration returned by
    ``SimpleParser()``.
    """
    
    def tokens(self, parser):
        return ((PlusMinusPlugin.Plus, 0), (PlusMinusPlugin.Minus, 0))
    
    def filters(self, parser):
        return ((PlusMinusPlugin.do_plusminus, 510), )
    
    @staticmethod
    def do_plusminus(parser, stream):
        required = AndGroup()
        optional = OrGroup()
        prohibited = OrGroup()
        
        nextlist = optional
        for t in stream:
            if isinstance(t, PlusMinusPlugin.Plus):
                nextlist = required
            elif isinstance(t, PlusMinusPlugin.Minus):
                nextlist = prohibited
            else:
                nextlist.append(t)
                nextlist = optional
        
        r = optional
        if required:
            r = AndMaybeGroup([required, optional])
        if prohibited:
            r = AndNotGroup([r, prohibited])
        return r
    
    class Plus(Singleton):
        expr = rcompile("\\+")
        
    class Minus(Singleton):
        expr = rcompile("-")


class MultifieldPlugin(Plugin):
    """Converts any unfielded terms into OR clauses that search for the
    term in a specified list of fields.
    """
    
    def __init__(self, fieldnames, fieldboosts=None):
        """
        :param fieldnames: a list of fields to search.
        :param fieldboosts: an optional dictionary mapping field names to
            a boost to use for that field.
        """
        
        self.fieldnames = fieldnames
        self.boosts = fieldboosts or {}
    
    def filters(self, parser):
        return ((self.do_multifield, 110), )
    
    def do_multifield(self, parser, stream):
        newstream = stream.empty()
        for t in stream:
            if isinstance(t, BasicSyntax) and t.fieldname is None:
                t = OrGroup([t.set_fieldname(fn).set_boost(self.boosts.get(fn, 1.0))
                             for fn in self.fieldnames])
            newstream.append(t)
        return newstream
        

class DisMaxPlugin(Plugin):
    """Converts any unfielded terms into DisjunctionMax clauses that search
    for the term in a specified list of fields.
    """
    
    def __init__(self, fieldboosts, tiebreak=0.0):
        """
        :param fieldboosts: a dictionary mapping field names to a boost to use
            for that in the DisjuctionMax query.
        """
        
        self.fieldboosts = fieldboosts.items()
        self.tiebreak = tiebreak
    
    def filters(self, parser):
        return ((self.do_dismax, 110), )
    
    def do_dismax(self, parser, stream):
        newstream = stream.empty()
        for t in stream:
            if isinstance(t, BasicSyntax) and t.fieldname is None:
                t = DisMaxGroup([t.set_fieldname(fn).set_boost(b)
                                 for fn, b in self.fieldboosts],
                                 tiebreak=self.tiebreak)
            newstream.append(t)
        return newstream


class FieldAliasPlugin(Plugin):
    """Adds the ability to use "aliases" of fields in the query string.
    
    >>> # Allow users to use 'body' or 'text' to refer to the 'content' field
    >>> parser.add_plugin(FieldAliasPlugin({"content": ("body", "text")}))
    >>> parser.parse("text:hello")
    Term("content", "hello")
    """
    
    def __init__(self, fieldmap):
        """
        :param fieldmap: a dictionary mapping fieldnames to a list of
            aliases for the field.
        """
        
        self.fieldmap = fieldmap
        self.reverse = {}
        for key, values in fieldmap.iteritems():
            for value in values:
                self.reverse[value] = key
        
    def filters(self, parser):
        return ((self.do_aliases, 90), )
    
    def do_aliases(self, parser, stream):
        newstream = stream.empty()
        for t in stream:
            if (not isinstance(t, Group)
                  and t.fieldname is not None
                  and t.fieldname in self.reverse):
                    t = t.set_fieldname(self.reverse[t.fieldname])
            newstream.append(t)
        return newstream


class CopyFieldPlugin(Plugin):
    """Looks for basic syntax tokens (terms, prefixes, wildcards, phrases, etc.)
    occurring in a certain field and replaces it with a group (by default OR)
    containing the original token and the token copied to a new field.
    
    For example, the query::
    
        hello name:matt
        
    could be automatically converted by ``CopyFieldPlugin({"name", "author"})``
    to::
    
        hello (name:matt OR author:matt)
    
    This is useful where one field was indexed with a differently-analyzed copy
    of another, and you want the query to search both fields.
    """
    
    def __init__(self, map, group=OrGroup, mirror=False):
        """
        :param map: a dictionary mapping names of fields to copy to the
            names of the destination fields.
        :param group: the type of group to create in place of the original
            token.
        :param two_way: if True, the plugin copies both ways, so if the user
            specifies a query in the 'toname' field, it will be copied to
            the 'fromname' field.
        """
        self.map = map
        self.group = group
        self.mirror = mirror
        
    def filters(self, parser):
        return ((self.do_copyfield, 109), )
    
    def do_copyfield(self, parser, stream):
        mirror = self.mirror
        map = self.map
        if mirror:
            # Add in reversed mappings
            map.update(dict((v, k) for k, v in map.iteritems()))
        
        newstream = stream.empty()
        for t in stream:
            if isinstance(t, Group):
                t = self.do_copyfield(parser, t)
            elif isinstance(t, BasicSyntax):
                toname = None
                if t.fieldname in map:
                    toname = map[t.fieldname]
                elif t.fieldname is None and parser.fieldname in map:
                    toname = map[parser.fieldname]
                
                if toname:
                    # Replace the syntax object with a group containing the
                    # original object and one with the field changed
                    t = self.group([t, t.set_fieldname(toname, force=True)])
            newstream.append(t)
        return newstream









