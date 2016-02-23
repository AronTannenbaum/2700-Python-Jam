#!/usr/bin/env python
"""Context-Free Grammar parser for generic text generation

Usage: python cfg.py [options] [source]

Options:
  -g ..., --grammar=...   use specified grammar file or URL
  -r [num], --repeat=...  repeates with the specified delay (in seconds)
  -h, --help              show this help

Examples:
  cfg.py                       generates from the default grammar 
                                 (assumed to be ./grammar.xml)
  cfg.py "<mygrammarnode />"   generates from the specified node or string
  cfg.py -g mygrammar.xml      generates from the specified grammar file
  cfg.py -r 4                  repeats with a 4s delay between generations

"""

from xml.dom import minidom
import random
import toolbox
import sys
import getopt
import re
import time

class NoSourceError(Exception): pass

class CFG:
    def __init__(self, grammar, source=None):
        self.reset()
        self.loadGrammar(grammar)
        self.loadSource(source and source or '<main/>')
        self.parse(self.source)

    def _load(self, source):
        """XML input source can be:
        - a URL of a remote XML file        ("http://.../grammar.xml")
        - a filename of a local XML file    ("~/.../grammar.xml")
        - standard input                    ("-")
        - the actual XML, as a string       ("<choice><s>Dog</s><s>Cat</s></choice>")
        """
        try:
            sock = toolbox.openAnything(source)
            xmldoc = minidom.parse(sock).documentElement
            sock.close()
        except:
            print "There is an error in the grammar file \"" + source + "\""
            sys.exit(2)
        return xmldoc

    def loadGrammar(self, grammar):
        self.grammar = self._load(grammar)
        self.refs = {}
        for ref in self.grammar.childNodes:
            self.refs[ref.nodeName] = ref
            
    def loadSource(self, source):
        self.source = self._load(source)

    def reset(self):
        self.pieces = []
        self.memory = {}
        self.store = {}
        self.capitalizeNext = 0
        self.pluralizeNext = 0

    def randomChildElement(self, node):
        """choose a random child element of a node
        
        This is a utility method used by do_xref and do_choice.
        """
        choices = [e for e in node.childNodes
                   if e.nodeType == e.ELEMENT_NODE]
        chosen = random.choice(choices)
        return chosen

    def parse(self, node):
        """parse a single XML node
        
        Construct the name of a class method based on the type
        of node we're parsing and call the method.
        """
        parseMethod = getattr(self, "parse%s" % node.__class__.__name__)
        parseMethod(node)

    def parseDocument(self, node):
        """parse the document node"""
        self.parse(node.documentElement)

    def parseText(self, node):
        """parse a text node
        
        The text of a text node is added to the output buffer.  
        We also manage any memorized variables that need to be addended.
        """
        self.appendContent(node.data)

    def parseElement(self, node):
        """parse an element
        
        An XML element corresponds to an actual tag in the source.
        Each element type is handled in its own method. 
        """
        methodName = node.tagName[0].upper() + node.tagName[1:].lower()
        try:
            handlerMethod = getattr(self, "handle%s" % methodName)
        except:
            handlerMethod = getattr(self, "handleRef")
        handlerMethod(node)

    def handleRef(self, node):
        """handle any user-defined tag"""
        self.parse(self.randomChildElement(self.refs[node.nodeName]))

    def handleExtern(self, node):
        """handle <extern> tag
        
        The <extern> tag specifies an external grammar and source to parse.
        
        Attributes we care about:
        
        grammar="[name]"        the location of the grammar
        source="[string]"       the name of the element in the grammar to evaluate.
        
        NOTE: this tag may  be extended to support RPCs as well as grammars.
        """
        keys = node.attributes.keys()
        
        if "grammar" in keys:
            grammar = node.attributes["grammar"].value
        if "source" in keys:
            source = '<' + node.attributes["source"].value + '/>'
            
        c = CFG(grammar, source)
        self.appendContent(c.output())

    def handleRecall(self, node):
        """handle <recall> tag
        
        The <recall> tag allows the grammar to recall values stored with the <s memory=""
        construction. Attributes we care about:
 
        memory="[name]"     recalls the value of the internal variable with name [name]
        """
        keys = node.attributes.keys()
        if "memory" in keys:
            self.appendContent(self.memory[node.attributes["memory"].value]["value"])
               
    def handleS(self, node):
        """handle <s> tag, the core of the grammar.
        
        Attributes we care about:
        
        caps="true"         capitalizes the first letter of the next word after the tag.
                            other valid values are "yes" and "1"
        chance="X"          enforces an X% chance the tag will be evaluated
        memory="[name]"     stores the value of the evaluated tag in an internal    
                            variable with name [name], to be recalled with the 
                            <recall memory="[name]" /> tag
        """
        keys = node.attributes.keys()
        continueParse = 1
        if "caps" in keys:
            if node.attributes["caps"].value == "true" or node.attributes["caps"].value == "1" or node.attributes["caps"].value == "yes":
                self.capitalizeNext = 1
        if "c" in keys:
            if node.attributes["c"].value == "true" or node.attributes["c"].value == "1" or node.attributes["c"].value == "yes":
                self.capitalizeNext = 1
        if "plural" in keys:
            if node.attributes["plural"].value == "true" or node.attributes["plural"].value == "1" or node.attributes["plural"].value == "yes":
                self.pluralizeNext = 1
        if "p" in keys:
            if node.attributes["p"].value == "true" or node.attributes["p"].value == "1" or node.attributes["p"].value == "yes":
                self.pluralizeNext = 1
        if "chance" in keys:
            chance = int(node.attributes["chance"].value)
            continueParse = (chance > random.randrange(100))
            #if not continueParse: self.appendContent("DDD")
        if continueParse:
            if "memory" in keys:
                self.store = node.attributes["memory"].value
                self.memory[self.store] = {'size':0, 'value':""}
                self.memory[self.store]["size"] = node.childNodes.length 
            for child in node.childNodes: 
                self.parse(child)

    def handleChoice(self, node):
        """handle <choice> tag
        
        A <choice> tag contains one or more <s> tags.  One is chosen at random and evaluated.
        """
        self.parse(self.randomChildElement(node))

#    def handleComment(self, node):
#        """handle <!-- comment --> tag
#        
#        i.e., ignore it.
#        """
#        self.parse("")
        
    def appendContent(self, text):
        """appends the value of text to the result
        
        Also manages any memory variables to insure they are completed.
        """
        newText = text
        if self.capitalizeNext:
            newText = text[0].upper() + text[1:]
            text = newText
            #self.pieces.append(text[0].upper())
            #self.pieces.append(text[1:])
            self.capitalizeNext = 0
        if self.pluralizeNext:
            if re.search('(ch|sh|s|z|x)$', text):
                pl = text + 'es'
            elif re.search('[bcdfghjklmnpqrstvwxz]y$', text):
                pl = text[:-1] + 'ies'
            elif re.search('[^o]o$', text):
                pl = text + 'es'
            else:
                pl = text + 's'
            newText = pl
            self.pluralizeNext = 0
        for key in self.memory.keys():
             if self.memory[key]["size"] > 0:
                self.memory[key]["value"] += text
                self.memory[key]["size"] -= 1
        self.pieces.append(newText)

    def output(self):
        """output generated text"""
        s = re.sub("[ ][ ]+", " ", "".join(self.pieces).strip())
        # replace out foibles
        #s = s.replace("ys ", "ies ")
        #s = s.replace("ys\n", "ies\n")
        s = s.replace("a e", "an e")
        s = s.replace("a a", "an a")
        s = s.replace("a o", "an o")
        s = s.replace("a i", "an i")
        s = s.replace("a u", "an u")
        s = s.replace("A e", "An e")
        s = s.replace("A a", "An a")
        s = s.replace("A o", "An o")
        s = s.replace("A i", "An i")
        s = s.replace("A u", "An u")
        s = s.replace("eing", "ing")
        #s = s.replace("fs ", "ves")
        #s = s.replace("fs\n", "ves\n")
        #s = s.replace("sss", "ss")
        return s

def usage():
    print __doc__

def main(argv):
    grammar = "grammar.xml"
    delay = -1
        
    try:
        opts, args = getopt.getopt(argv, "hg:r:", ["help", "grammar=", "repeat="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-r", "--repeat"):
            try:
                delay = float(arg)
            except:
                print "invalid argument -r " + arg
                sys.exit(2)
        elif opt in ("-g", "--grammar"):
            grammar = arg
    
    source = "".join(args)
    while (1):
        c = CFG(grammar, source)
        print c.output()
        if delay > -1:
            print
            time.sleep(delay)
        else:
            sys.exit()

if __name__ == "__main__":
    main(sys.argv[1:])
