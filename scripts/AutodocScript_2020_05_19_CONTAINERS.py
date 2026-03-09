#################################
### Execution Enviornment ##
alteryxEnv = True
debug = True

if alteryxEnv:
    from ayx import Package
    from ayx import Alteryx

import json 
import os
import pandas as pd
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import re


try:
    import xmltodict
    from PIL import Image, ImageDraw,ImageFont
except:
    if alteryxEnv:
        Package.installPackages(['xmltodict','pillow'])
    import xmltodict
    from PIL import Image, ImageDraw, ImageFont






class Node:

    #This constructor is awful
    def __init__(self,node,imageMapping=None, isChild=0, parentContainer=None):
        self.nodeId = node["@ToolID"]
        #print("Created node ID {}".format(self.nodeId))
        self.nodeType = None
        if 'EngineSettings' in node.keys():
            if '@Macro' in node['EngineSettings']:
                if '\\' in node['EngineSettings']['@Macro']:
                    self.nodeType = node['EngineSettings']['@Macro'].split("\\")[-1].split(".")[0]
                else:
                    self.nodeType = node['EngineSettings']['@Macro'].split(".")[0]
            elif '@Plugin' in node["GuiSettings"].keys():
                self.nodeType = node["GuiSettings"]["@Plugin"].split(".")[-1]
                if len(self.nodeType) < 3: # Assume we messed something up and just got a version number 
                    self.nodeType = node["GuiSettings"]["@Plugin"]
            else:
                self.nodeType = 'Macro'  
        elif '@Plugin' in node["GuiSettings"].keys():
            self.nodeType = node["GuiSettings"]["@Plugin"].split(".")[-1]
        else:
            self.nodeType = 'Macro'

        self.positionX = float(node["GuiSettings"]["Position"]['@x'])
        self.positionY = float(node["GuiSettings"]["Position"]['@y'])
        self.width = None 
        if '@width' in node["GuiSettings"]["Position"].keys():
            self.width = float(node["GuiSettings"]["Position"]['@width'])
        self.height = None 
        if '@height' in node["GuiSettings"]["Position"].keys():
            self.height = float(node["GuiSettings"]["Position"]['@height']) 
        self.annotations = None
        if 'AnnotationText' in node["Properties"]["Annotation"].keys():
            self.annotations = node["Properties"]["Annotation"]["AnnotationText"]
        elif 'DefaultAnnotationText' in node["Properties"]["Annotation"].keys():
            self.annotations = node["Properties"]["Annotation"]["DefaultAnnotationText"]
        else:
            self.annotations = ""
        self.configuration = None 
        if 'Configuration' in node["Properties"].keys():
            self.configuration = node["Properties"]["Configuration"] # this will be json stuff
        self.metaInfo = None 
        if 'MetaInfo' in node["Properties"].keys():
            self.metaInfo = node["Properties"]["MetaInfo"]
        self.imageMapping = imageMapping
        self.isChild = int(isChild) 

        self.text = ""
        if self.nodeType == 'TextBox':
            if 'Text' in self.configuration:
                if self.configuration['Text'] is not None:
                    self.text += self.configuration['Text']
        if self.nodeType == 'ToolContainer':
            if 'Caption' in self.configuration:
                if self.configuration['Caption'] is not None:
                    self.text += self.configuration['Caption']

        self.max_X = self.positionX
        if self.width is not None:
            self.max_X += self.width
        
        self.max_Y = self.positionY
        if self.height is not None:
            self.max_Y += self.height

        self.parentContainer = parentContainer 
        self.topContainer = None
        self.nodeDependencies = None
        self.isDisabled = False

        #If container, check if disabled
        if self.nodeType == 'ToolContainer':
            if self.configuration['Disabled']['@value'] == 'True':
                self.isDisabled=True
        
        #If the parent is disabled, the tool is disabled
        if self.parentContainer is not None:
            if self.parentContainer.isDisabled == True:
                self.isDisabled = True

        self.formulas = []
        if self.nodeType=='Formula' or self.nodeType=='LockInFormula':
            if type(self.configuration['FormulaFields']['FormulaField']) == type(dict({'placeholder':dict})):
                #There is one formula
                f = self.configuration['FormulaFields']['FormulaField']
                self.formulas.append("({2}) {0} = {1}".format(f['@field'],f['@expression'],f['@type']))
                #self.formulas.append( {"formula":f['@expression'], "field":f['@field'], "datatype":f['@type']+" - "+f['@size'] } )
            
            if type(self.configuration['FormulaFields']['FormulaField'])==type(list(['placeholder','list'])):
                #there are multiple formulae
                for f in self.configuration['FormulaFields']['FormulaField']:
                    self.formulas.append("({2}) {0} = {1}".format(f['@field'],f['@expression'],f['@type']))
        elif self.nodeType=="Filter":
            if 'Expression' in self.configuration:
                self.formulas.append(self.configuration['Expression'])
        elif self.nodeType=="MultiRowFormula":
            if 'Expression' in self.configuration:
                if self.configuration['UpdateField']['@value']=='True':
                    self.formulas.append("{0} = {1}".format(self.configuration["UpdateField_Name"],self.configuration['Expression']))
                else:
                    self.formulas.append("({2}) {0} = {1}".format(self.configuration["CreateField_Name"],self.configuration['Expression'], self.configuration['CreateField_Type']))
        elif self.nodeType=="MultiFieldFormula":
            if 'Expression' in self.configuration and 'Fields' in self.configuration:
                self.formulas.append(self.configuration['Expression'])
        else:
            self.formulas.append(None)

        #Get Fields and Tables#
        self.fields=[]
        self.tables=[]
        if self.nodeType in ['DbFileInput', 'DbFileOutput']:
            if 'File' in self.configuration:
                if '#text' in self.configuration['File']:
                    self.queryHandler(self.configuration['File']['#text'])
            if self.metaInfo is not None:
                if 'RecordInfo' in self.metaInfo:
                    if 'Field' in self.metaInfo['RecordInfo']:
                        #check if list of fields or single field
                        # 6/14/2019 added ' for field names, can use space for delim (except between ')
                        if type(self.metaInfo['RecordInfo']['Field']) == type(list(["a","b"])):
                            for field in self.metaInfo['RecordInfo']['Field']:
                                self.fields.append("({1}) [{0}]".format(field['@name'],field['@type']))
                        else:
                            field = self.metaInfo['RecordInfo']['Field']
                            self.fields.append("({1}) [{0}]".format(field['@name'],field['@type']))

        if self.nodeType in ['AlteryxSelect','AppendFields','Join','JoinMultiple']:
            if 'SelectFields' in self.configuration or 'SelectFields' in self.configuration['SelectConfiguration']['Configuration']:
                if self.nodeType =='AlteryxSelect':
                    SelectedFields = self.configuration['SelectFields']
                elif self.nodeType in ['Join','AppendFields','JoinMultiple']:
                    SelectedFields = self.configuration['SelectConfiguration']['Configuration']['SelectFields']
                for SelectField in SelectedFields:
                    SelectField = SelectedFields['SelectField']
                    if type(SelectField) == type(list([])):
                        for item in SelectField:
                            #print(item)
                            field = ""
                            selected = ""
                            rename = ""
                            size = ""
                            fieldtype=""
                            if '@field' in item:
                                field = item['@field']
                            if '@selected' in item:
                                selected=item['@selected']
                            if '@rename' in item:
                                rename=item['@rename']
                            if '@size' in item:
                                size=item['@size']
                            if '@type' in item:
                                fieldtype=item['@type']
                            appendstring = "[{0}]|".format(field) + "{0}|".format(selected)  + "{0}|".format(size)+ "{0}|".format(rename) + "{0}".format(fieldtype)
                            self.fields.append(appendstring)
                            #self.fields.append("({1}) [{0}] [{2}] [{3}] [{4}]".format(field,fieldtype,size,selected,rename))
                    else:
                        item=SelectField
                        field = ""
                        selected = ""
                        rename = ""
                        size = ""
                        fieldtype=""
                        if '@field' in item:
                            field = item['@field']
                        if '@selected' in item:
                            selected=item['@selected']
                        if '@rename' in item:
                            rename=item['@rename']
                        if '@size' in item:
                            size=item['@size']
                        if '@type' in item:
                            fieldtype=item['@type']
                        appendstring = "[{0}]|".format(field) + "{0}|".format(selected)  + "{0}|".format(size)+ "{0}|".format(rename) + "{0}".format(fieldtype)
                        self.fields.append(appendstring)
                        #self.fields.append("({1}) [{0}] [{2}] [{3}] [{4}]".format(field,fieldtype,size,selected,rename))

    def queryHandler(self, s):
        #TODO:
        #Method to determine if something is a query or file
        #Parse fields and tables if query
        self.tables.append(s)
        



class Connection:
    
    def __init__(self, con, nodelist, connectionName=None, isWireless=False):
        self.originNodeId = con['Origin']['@ToolID']
        self.destinationNodeId = con['Destination']['@ToolID']
        self.connectionName = connectionName
        self.isWireless = isWireless
        self.originConnection = None
        if '@Connection' in con['Origin'].keys():
            self.originConnection=con['Origin']['@Connection']
        self.destinationConnection = None
        if '@Connection' in con['Destination'].keys():
            self.destinationConnection = con['Destination']['@Connection']

        for n in nodelist:
            if n.nodeId == self.originNodeId:
                self.originNode = n
            if n.nodeId == self.destinationNodeId:
                self.destinationNode = n
        #
        # print("Created connection from node {0} to node {1}".format(self.originNode.nodeId,self.destinationNode.nodeId))

    #Method to get X,Y coods of origin node and destination node
    def getCoords(self):
        x1 = self.originNode.positionX+42
        y1 = self.originNode.positionY+18
        x2 = self.destinationNode.positionX
        y2 = self.destinationNode.positionY+18
        return [x1,y1,x2,y2]


class Workflow:

    def __init__(self, filePath):
        self.filePath = filePath
        self.nodes = [] # This is a list of nodes
        self.connections = [] # This is a list of connections

    def parseWorkflow(self, imlibpath):
        try:
            with open(self.filePath) as fd:
                fd.readline() # Drop the first line #
                dat = fd.read()
                self.doc = xmltodict.parse(dat,dict_constructor=dict,encoding='utf-8')
        except:
            with open(self.filePath, encoding="utf8") as fd:
                fd.readline() # Drop the first line #
                dat = fd.read()
                self.doc = xmltodict.parse(dat,dict_constructor=dict,encoding='utf-8')

        # Determine Canvas Size #
        # Collect Nodes #
        if self.doc["AlteryxDocument"]["Nodes"] is not None:
            self.collectNodes(self.doc["AlteryxDocument"]["Nodes"],self.nodes)
            self.max_x = max(int(max([node.max_X for node in self.nodes]) + 200), 500)
            self.max_y = max(int(max([node.max_Y for node in self.nodes]) + 200), 300)
            self.max_level = max([node.isChild for node in self.nodes])
        else:
            self.max_x = 500
            self.max_y = 300
            self.max_level = 0

        #Get Connections
        if self.doc["AlteryxDocument"]["Connections"] is not None:
            self.collectConnections(self.doc["AlteryxDocument"]["Connections"],self.nodes,self.connections)

        #Populate image library
        self.imLib = self.getImageLibrary(self.nodes,configPath=imlibpath)

        return self   


    # Method to collect Nodes #
    def collectNodes(self, nodes, li, level = 0, parentContainer = None):
        if nodes is not None:
            if len(nodes["Node"])>1 and type(nodes["Node"])==type(list(["placeholder","list"])):
                for node in nodes["Node"]:
                    n = Node(node,isChild=level, parentContainer=parentContainer)
                    li.append(n)
                    if '@Plugin' in node["GuiSettings"].keys():
                        #Recursive Container Search
                        if "ToolContainer" in node["GuiSettings"]["@Plugin"] and "ChildNodes" in node.keys():
                            self.collectNodes(node["ChildNodes"],li,level = level + 1, parentContainer=n)
            elif len(nodes["Node"])==1 or type(nodes["Node"])==type({"placeholder":"dictionary"}):
                node = nodes["Node"]
                #print(node)
                n = Node(node,isChild=level, parentContainer=parentContainer)
                li.append(n)
                if '@Plugin' in node["GuiSettings"].keys():
                    #Recursive Container Search
                    if "ToolContainer" in node["GuiSettings"]["@Plugin"] and "ChildNodes" in node.keys():
                        self.collectNodes(node["ChildNodes"],li,level = level + 1, parentContainer=n)
            else:
                #No Node Found
                pass

    # Method to collect connections #
    def collectConnections(self, connections, nodelist, li):

        def getConnection(con, li=li,nodelist=nodelist):
            name = None
            if '@name' in con.keys():
                name=con['@name']
            wireless = False
            if '@Wireless' in con.keys():
                wireless=True
            connection = Connection(con,nodelist,name,wireless)
            li.append(connection)


        if len(connections['Connection'])>1 and type(connections['Connection'])==type(list(['placeholder','list'])):
            for con in connections["Connection"]:
                getConnection(con)

        elif len(connections['Connection'])==1 or type(connections['Connection'])==type(dict({'placeholder':'dict'})):
            con = connections["Connection"]
            getConnection(con)

        else:
            #No connections exist
            pass

    # Method to build image library #
    def getImageLibrary(self, nodes, configPath='config/imageMapping.json'):

        images = {}
        nodeTypes = set([node.nodeType for node in nodes])

        #get the manual path mapping
        with open(configPath) as json_file:  
            pathMapping = json.load(json_file)

        imageBasePath = os.path.dirname(os.path.dirname(configPath))+"/"

        images['input'] = Image.open(imageBasePath+'img/input_anchor.png').resize((10,10),resample=Image.LANCZOS)
        images['output'] = Image.open(imageBasePath+'img/output_anchor.png').resize((10,10),resample=Image.LANCZOS)

        for n in nodeTypes:
            if n in pathMapping.keys():
                images[n] = Image.open(imageBasePath+pathMapping[n]).resize((42,36),resample=Image.LANCZOS)
            else:
                try:
                    images[n] = Image.open(imageBasePath+'img/'+n+".png").resize((42,36),resample=Image.LANCZOS)
                except:
                    #No Image Found
                    pass
                    #images[n] = Image.open('img/UnknownTool.png').resize((42,36),resample=Image.LANCZOS)
        return images

    def wrapText(self, caption,maxWidth):
        lines = []
        words = caption.replace("\n"," \n ").split(" ")
        #keep track of running length
        runningTotal = 0
        for word in words:
            if word == '\n':
                lines.append(word)
                runningTotal = 0
            elif len(word) + runningTotal > int(maxWidth):
                lines.append("\n")
                lines.append(word)
                runningTotal = 0 + len(word)
            else:
                lines.append(word)
                runningTotal += len(word)
        return " ".join(lines).replace("\n ","\n")

    def rounded_rectangle(self, d, xy, corner_radius, fill=None, outline=None):
        upper_left_point = xy[0]
        bottom_right_point = xy[1]
        d.rectangle(
            [
                (upper_left_point[0], upper_left_point[1] + corner_radius),
                (bottom_right_point[0], bottom_right_point[1] - corner_radius)
            ],
            fill=fill,
            outline=outline
        )
        d.rectangle(
            [
                (upper_left_point[0] + corner_radius, upper_left_point[1]),
                (bottom_right_point[0] - corner_radius, bottom_right_point[1])
            ],
            fill=fill,
            outline=outline
        )
        d.pieslice([upper_left_point, (upper_left_point[0] + corner_radius * 2, upper_left_point[1] + corner_radius * 2)],
            180,
            270,
            fill=fill,
            outline=outline
        )
        d.pieslice([(bottom_right_point[0] - corner_radius * 2, bottom_right_point[1] - corner_radius * 2), bottom_right_point],
            0,
            90,
            fill=fill,
            outline=outline
        )
        d.pieslice([(upper_left_point[0], bottom_right_point[1] - corner_radius * 2), (upper_left_point[0] + corner_radius * 2, bottom_right_point[1])],
            90,
            180,
            fill=fill,
            outline=outline
        )
        d.pieslice([(bottom_right_point[0] - corner_radius * 2, upper_left_point[1]), (bottom_right_point[0], upper_left_point[1] + corner_radius * 2)],
            270,
            360,
            fill=fill,
            outline=outline
        )
        d.rectangle(
        [
            (upper_left_point[0] + corner_radius - 1, upper_left_point[1] + 1),
            (bottom_right_point[0] - corner_radius + 1, bottom_right_point[1] - 1)
        ],
        fill=fill,
        outline=fill
        )
        d.rectangle(
        [
            (upper_left_point[0] + 1, upper_left_point[1] + corner_radius),
            (bottom_right_point[0] - 1, bottom_right_point[1] - corner_radius)
        ],
        fill=fill,
        outline=fill
        )     

    def drawCurvyLine(self, d, coords, fill=(0,0,0), width=1):
        xS,yS,xE,yE = coords[0],coords[1],coords[2],coords[3]
        #Connections from and into tools should have this much length of straight line
        lineBuffer = 20
        rad = int(lineBuffer/2)
        lineDrawBuffer = int(lineBuffer/3)
        
        #Get New Coordinates
        xN = xS + lineBuffer #x New to keep track of current position
        yN = yS              #y New to keep track of current position

        xT = xE - lineBuffer #x Target
        yT = yE              #y Target
        #Draw Line

        if xS < xE and abs(yN-yT) < lineBuffer:
            pass
        else: 
            d.line([xS,yS,xN+lineDrawBuffer,yN],fill=fill,width=width)
            d.line([xE,yE,xT-lineDrawBuffer,yT],fill=fill,width=width)
    
        # possibilities:
        # y equal, xT < xN, xT > xN, xT = xN
        if abs(yN-yT) < lineBuffer and xS < xE:
            d.line([xS,yN,xE,yT], fill=fill, width=width)
        # yT > yN, xT < xN, xT > xN, xT = xN
        elif yT > yN:

            #xT<xN
            if xT < xN + lineBuffer:
                # S shape, 4 corners, target is below and to the left
                #First curve down
                d.arc([xN,yN,xN+rad,yN+rad],270, 360, fill=fill)
                xN, yN = xN+rad, yN+rad
                #Draw a line half way minus linebuffer to target
                d.line([xN, yN - lineDrawBuffer, xN, yN + ((yT-yN)/2) - lineBuffer + lineDrawBuffer],fill=fill,width=width)
                xN, yN = xN, yN + ((yT-yN)/2) - lineBuffer
                #Curve to the left
                d.arc([xN-rad,yN,xN,yN+rad],0,90,fill=fill)
                xN, yN = xN-rad,yN+rad
                #Draw line going left
                d.line([xN+lineDrawBuffer,yN,xT-lineDrawBuffer,yN],fill=fill,width=width)
                xN, yN = xT, yN
                #Arc turning from right down
                d.arc([xN-rad, yN, xN, yN+rad],180,270,fill=fill)
                xN,yN = xN-rad, yN+rad
                #Line going straight down
                d.line([xN,yN - lineDrawBuffer,xN,yT-rad + lineDrawBuffer],fill=fill,width=width)
                xN,yN = xN,yT-rad
                #Final curve
                d.arc([xN,yN,xN+rad,yN+rad],90,180,fill=fill)
                xN, yN = xN+rad,yN+rad

                #Final Check
                d.line([xN - lineDrawBuffer,yN,xT,yT],fill=fill,width=width) 

            #xT>xN+lineBuffer
            else:
                # just two corners
                #First curve down
                d.arc([xN,yN,xN+rad,yN+rad],270, 360, fill=fill)
                xN, yN = xN+rad, yN+rad
                #Line going straight down
                d.line([xN,yN - lineDrawBuffer,xN,yT-rad+lineDrawBuffer],fill=fill,width=width)
                xN,yN = xN,yT-rad
                #Final curve
                d.arc([xN,yN,xN+rad,yN+rad],90,180,fill=fill)
                xN, yN = xN+rad,yN+rad

                #Final Check
                d.line([xN - lineDrawBuffer,yN,xT,yT],fill=fill,width=width)           
                

        # yT < xN, xT < xN, xT > xN, xT = xN
        else:
            #xT<xN
            if xT < xN + lineBuffer:
                # S shape, 4 corners
                #Curve to the up
                d.arc([xN,yN-rad,xN+rad,yN],0,90,fill=fill)
                xN, yN = xN+rad,yN-rad

                #Line going up
                d.line([xN, yN + lineDrawBuffer, xN, yN - ((yN-yT)/2) + lineBuffer - lineDrawBuffer],fill=fill,width=width)
                xN, yN = xN, yN - ((yN-yT)/2) + lineBuffer

                #Turn Left
                d.arc([xN-rad,yN-rad,xN,yN],270, 0, fill=fill)
                xN, yN = xN-rad, yN-rad

                #Draw line going left
                d.line([xN,yN,xT-rad,yN],fill=fill,width=width)
                xN, yN = xT-rad, yN

                #Curve up
                d.arc([xN-rad,yN-rad,xN,yN],90,180,fill=fill)
                xN, yN = xN-rad,yN-rad   

                #Line up
                d.line([xN,yN+lineDrawBuffer,xN,yT+rad-lineDrawBuffer],fill=fill,width=width)
                xN,yN = xN,yT+rad 

                #Final Curve       
                d.arc([xN, yN-rad, xN+rad, yN],180,270,fill=fill)
                xN,yN = xN+rad, yN-rad

                #Final Check
                d.line([xN - lineDrawBuffer,yN,xT,yT],fill=fill,width=width)  

            #xT>xN+lineBuffer
            else:
                # just two corners
                #Curve to the up
                d.arc([xN,yN-rad,xN+rad,yN],0,90,fill=fill)
                xN, yN = xN+rad,yN-rad
                
                #Line going up
                d.line([xN, yN + lineDrawBuffer, xN, yT + rad - lineDrawBuffer],fill=fill,width=width)
                xN, yN = xN, yT + rad

                #Curve right
                d.arc([xN,yN-rad,xN+rad,yN],180,270,fill=fill)
                xN, yN = xN+rad,yN-rad

                #Final Check
                d.line([xN - lineDrawBuffer,yN,xT,yT],fill=fill,width=width)
    

    # How to determine what order the nodes are running in? #
    # TODO: Interface tools should probably come first 
    def getOrder(self, nodes,connections):
        #Get List of Nodes and list every incoming and outgoing edge per node
        allNodes = {}
        allEdges = {}
        #{42: {"Incoming":[1,2,3], "Outgoing":[123]}}
        for n in nodes:
            #Exclude Comments and Tool Containers
            if n.nodeType not in ['ToolContainer','TextBox','Tab','Label','LabelGroup']:
                allNodes[n.nodeId]={"nodeId":n.nodeId,"Incoming":[], "Outgoing":[], "IncomingCount":0}

        for i in range(0,len(connections)):
            allEdges[i] = {"orig":connections[i].originNodeId, "dest":connections[i].destinationNodeId} 
            allNodes[connections[i].originNodeId]['Outgoing'].append(i) 
            allNodes[connections[i].destinationNodeId]['Incoming'].append(i)
            allNodes[connections[i].destinationNodeId]['IncomingCount']+=1

        #Kahn's algorithm, Topological Sort
        L = [] # Sorted order of nodes
        S = [] # These nodes have no incoming edge

        # Populate S
        deleted_Nodes = []
        for n in allNodes:
            if allNodes[n]["IncomingCount"] == 0: #if there are 0 incoming connections
                S.append(allNodes[n])         #append this node to list S
                deleted_Nodes.append(n)
                #allNodes.pop(n, None)             #and remove this node from allNodes
        for n in deleted_Nodes:
            allNodes.pop(n,None)


        while len(S) > 0:
            L.append(S.pop(0))          #pop first item in S, append to the end of L
            this_node = L[-1]           #Grab  reference for the node we just moved
            k =  this_node['nodeId']    #id for this node

            delete_edges=[]
            for e in allEdges:
                if allEdges[e]['orig'] == k:        #if current node is origin for this edge
                    #remove this edge from the destination node
                    allNodes[allEdges[e]['dest']]["Incoming"].remove(e)
                    #reduce destination node incoming count by 1
                    allNodes[allEdges[e]['dest']]["IncomingCount"]-=1
                    #if incoming count is now 0, add this node to S and remove from all
                    if allNodes[allEdges[e]['dest']]["IncomingCount"] == 0:
                        S.append(allNodes.pop(allEdges[e]['dest'],None))
                    #delete this edge from allEdges
                    delete_edges.append(e)                    
                    #allEdges.pop(ek,None) #Cannot pop dictionary while iterating
            for key in delete_edges:
                allEdges.pop(key,None)

        #print(iteration,allEdges,len(allEdges))
        if len(allEdges) > 0:
            return ["Error, possible cycle found"]
        else:
            return [n['nodeId'] for n in L]


    # Determine which nodes belong together in a group
    #   A group is a list of nodes that are all 'between' one of:
    #   DbFileInput, LockInInput,DbFileOutput, LockInOutput,Join, LockInJoin, JoinMultiple
    #   AppendFields,Union, LockInUnion,FindReplace,LockInMacroOutput, LockInMacroInput

    # get the node object for a given id    
    def getNodeById(self, nodeId):
        """Input nodeId value
        returns node object with this id"""
        for n in self.nodes:
            if str(n.nodeId) == str(nodeId):
                return n

    # given a node id list, return a list of node IDs that are "next" via a connection
    def getNextNodesFromCurrentId(self, nodeIdList):
        """Input LIST [] of nodeId values (not objects)
            returns LIST [] of nodeId values that have a destination connection originating at one of the nodes identified by the input ids"""
        nextNodes = []

        for nodeId in nodeIdList:
            for c in self.connections:
                if str(c.originNodeId) == str(nodeId):
                    nextNodes.append(str(c.destinationNodeId))
        
        return nextNodes

    def getPreviousNodesFromCurrentId(self, nodeIdList):
        """Input LIST [] of nodeId values (not objects)
            returns LIST [] of nodeId values that have an origin connection targeted to one of the nodes identified by the input ids"""
        previousNodes = []

        for nodeId in nodeIdList:
            for c in self.connections:
                if str(c.destinationNodeId) == str(nodeId):
                    previousNodes.append(str(c.originNodeId))
        
        return previousNodes


    def getSubflowsByContiner(self):
        """ Creates a pandas dataframe with columns nodeId and subFlowId
            only assigns subFlowId to nodes that have incoming connections (except containers with incoming action tool)
            subFlowId is a grouping based on membership in a top level containers OR having shared dependencies on a top level container"""
        # First alternate grouping option, make a container a group.
        # CONSIDER ONLY LEVEL 0 CONTAINERS as groups, else chaos may occur.

        # Procedure:
        # 1. Get all level 0 containers
        #   If there are none, the whole workflow is section -1
        # 2. Get all nodes
        # 3. for each node with a parentContainer, recursive search for level 0 parent (a container in list from step 1)
        #       if one is found, assign that node to group nodeId of parent container
        #       if no parent is found, perform recursive search for dependency on "parents"
        #       group key is list of all self containers + dependency containers
        #       else assign to group 0 (no containers, no container dependencies)

        # Lists of pairs of nodeId and groupId values
        nodeListGrouped = []
        # Don't assign these to a group
        noGroup = ['ToolContainer','TextBox','Tab','Label','LabelGroup']

        levelZContainers = [c for c in self.nodes if c.isChild==0 and 'ToolContainer' in c.nodeType]
        
        if not levelZContainers:
            # No top level containers, the whole workflow is one group:
            for node in self.nodes:
                if node.nodeType not in noGroup:
                    nodeListGrouped.append({"nodeId":node.nodeId,"subFlowId":0})     
        else:
            # Temporary set of groups
            nodeListTemp = []
            for node in self.nodes:
                if node.nodeType not in noGroup:
                    # For each node, create frozenset of dependencies- where the dependencies are either 0 or nodeId of level 0 container
                    node.nodeDependencies = self.getLevelZeroDependencies(node)
                    #print("Node {0} depends on {1}".format(node.nodeId,str(node.nodeDependencies)))
                    if len(node.nodeDependencies) == 1 and node.nodeDependencies[0] == self.getTopContainerForNode(node):
                        # This node's only dependency is its own container, flag it as somehow different
                        node.nodeDependencies[0] = -1 * node.nodeDependencies[0]
                    nodeListTemp.append({"nodeId":node.nodeId, "subFlowKey":frozenset(node.nodeDependencies)})

            # For each item in nodeListTemp, what is the actual order in which it gets run?
            nodeOrder = self.getOrder(self.nodes, self.connections)
            for item in nodeListTemp:
                item['itemOrder'] = nodeOrder.index(item['nodeId']) if item['nodeId'] in nodeOrder else None
                #print("node {0} in order {1} has key set {2}".format(item['nodeId'], item['itemOrder'],item['subFlowKey']))

            # Get the min itemOrder for each subFlowKey
            setToId = {}
            keyset = set([i['subFlowKey'] for i in nodeListTemp])
            # Map each subFlowKey (frozen set) to a minimum itemOrder value
            for k in keyset:
                mini = min([i['itemOrder'] for i in nodeListTemp if i['subFlowKey'] == k])
                setToId[k] = mini

            for item in nodeListTemp:
                item['subFlowId'] = setToId[item['subFlowKey']]
                nodeListGrouped.append({"nodeId":item['nodeId'], "subFlowId":item['subFlowId']})
        
        return pd.DataFrame(nodeListGrouped)

    
    def getLevelZeroDependencies(self, node):
        """Input a node OBJECT\n returns the list of nodeId values of the child-level-zero containers upon which this node depends\n
        should return a list of container nodeId values for each node (or the 0 node, which is the workflow itself)\n
        *Assumes that input node is not itself a container (or otherwise un-groupable item)*
        """
        # Make new empty list with every iteration
        dependencyList = []

        if node.nodeDependencies is not None:
            #print("Fetching dependency list from memory")
            return node.nodeDependencies
        else:
            this_container = int(self.getTopContainerForNode(node))
            # This node is in a container
            if this_container > 0:
                # nodeId value of this container added as entry in dependencyList
                dependencyList.append(this_container)
            else:
                # Get nodeId values list for all incoming nodes (using assumption above *)
                prevNodeList = self.getPreviousNodesFromCurrentId([node.nodeId])
                #print("Getting origin container for "+ node.nodeId +" previous Nodes are " + str(prevNodeList))
                # There are previous nodes
                if prevNodeList:
                    for n in prevNodeList:
                        # Recursive call
                        dependencyList.extend(self.getLevelZeroDependencies(self.getNodeById(n)))
                # There are no previous nodes left
                else:
                    #print("No previous nodes found")
                    dependencyList.append(0)

            return dependencyList

    
    # Helper method to find top container for node for getSubflowsByContiner
    def getTopContainerForNode(self, node):
        """Input node OBJECT (not id), 
        returns the nodeId value for the level 0 container containing this object if there is one
        otherwise returns 0"""
        if node.topContainer is not None:
            #print("Fetched top container node from memory ")
            return int(node.topContainer)
        else:
            if node.isChild == 0 and 'ToolContainer' in node.nodeType:
                # Found top container
                node.topContainer = int(node.nodeId)
                return int(node.nodeId)
            elif node.isChild > 0:
                # This node is a child, search up a level
                parentContainerNodeId = self.getTopContainerForNode(node.parentContainer)
                node.topContainer = parentContainerNodeId
                return parentContainerNodeId
            else:
                # This node is just hanging out on the canvas or has no top container
                return 0


    def getSubflows(self):
        # Create Groups #
        # Define Order of group:
        # Group A comes before Group B if the first node of A comes before the first node of B
        # Items that do not fall into a group but appear on the exec order form their own group

        #These nodes should be considered endpoints (not included in current flow)
        # Update: these are actually being used as "startpoints" but whatever man
        # add lift chart
        endpoints = ["FileBrowse","TextInput","Directory","RunCommand","Macro","DbFileInput","LockInInput","Join","LockInJoin","JoinMultiple","AppendFields","Union"," LockInUnion","FindReplace","LockInMacroInput"]
        #This is the starting list of all nodes in order (only nodes that are ordered)
        nodeOrder = self.getOrder(self.nodes, self.connections)
        #print(nodeOrder)
        #Search down order of nodes
        #if I find an endpoint, start a new group
        #recursively search for next nodes until there are no next nodes or every next node is an endpoint
        #save group, remove all these nodes from node order list
        #repeat until there are no nodes remaining in order of nodes list

        groupOrder = []

        while len(nodeOrder)>0:
            #print(len(nodeOrder),nodeOrder)
            index = 0
            startingNode = nodeOrder[index]
            group = None
                
            if self.getNodeById(startingNode).nodeType in endpoints:
                #Start recursive search proceedure
                group = [startingNode]
                #print(group[0],self.getNodeById(group[0]).nodeType)
                #initiate first search for nextNodes
                nextNodes = self.getNextNodesFromCurrentId(group)
                #While there are still nextNodes
                while len(nextNodes)>0:
                    #for each node in the list of next nodes
                    newNodes = []
                    for n in nextNodes:
                        #if the node is NOT an endpoint, add it to the current group
                        if self.getNodeById(n).nodeType not in endpoints:
                            group.append(n)
                            # keep track of what was newly added
                            newNodes.append(n)
                        #otherwise it is an endpoint, just take it out of the nextNodes list
                        else:
                            #Else just do nothing, it's an endpoint
                            pass
                            #Cant do this wth
                            #nextNodes.pop(nextNodes.index(n))

                    #repopulate nextNodes with the next nextNodes
                    nextNodes = self.getNextNodesFromCurrentId(newNodes)
                    # start at 298
                    #print(newNodes, " point to ", nextNodes)
                
                    #if this loop terminates, there are no next nodes (that are not an endpoint)
            else:
                #if we landed on an end without a start point, just go ahead and create it as a group
                group = [startingNode]
            #the group now contains all the nodes up to the endpoints
            #Add all elements of the group as the first element of groupOrder
            
            if group is not None and len(group)>0:
                #print("Removing group",group,"from",nodeOrder)
                #Add this group to the group order
                groupOrder.append(group.copy())
                #Remove these items from the nodeOrder
                while len(group)>0:
                    try:
                        nodeOrder.pop(nodeOrder.index(group.pop(0)))
                    except:
                        #sometimes the node is already removed from the node order
                        try:
                            group.pop(0)
                        except:
                            #We end up here when the try block successfully pops the node from the group but not the nodeOrder
                            pass
            
            #print(len(nodeOrder),"New Node Order:",nodeOrder)

        #print(groupOrder)
        flatNodeList = []
        groupNameList = []
        for j in range(len(groupOrder)):
            for k in groupOrder[j]:
                if k not in flatNodeList:
                    flatNodeList.append(k)
                    groupNameList.append(j)

        #grouped = pd.DataFrame([flatNodeList, groupNameList], columns=["nodeId","groupId"])
        grouped = pd.DataFrame()
        grouped['nodeId'] = flatNodeList
        grouped['subFlowId'] = groupNameList
        return grouped
                


    #Draw the Workflow
    def drawWorkflow(self, outpath):  

        #Draw Canvas
        self.img = Image.new('RGBA', (self.max_x, self.max_y), color = (255,255,255))
        self.d = ImageDraw.Draw(self.img)

        self.d.text((self.max_x-500,1), os.path.basename(self.filePath), fill=(200,200,200))
        self.d.text((self.max_x-500,11),"Workflow has been created by Alteryx Designer version {0}".format(self.doc["AlteryxDocument"]["@yxmdVer"]),fill=(200,200,200))
        self.d.text((self.max_x-500,21),"Imaging utility authored by Lev Solomovich (lev.solomovich@keyrus.us)",fill=(200,200,200))

        #The meat of the proceedure 
        for i in range(0,self.max_level+1):
            #Draw level 0, then 1, then 2, etc...
            for n in self.nodes:

                if n.nodeType == 'Tab':
                    continue

                if n.isChild == i:
                    #TOOL CONTAINERS
                    if 'ToolContainer' in n.nodeType:
                        #attempt to read caption
                        if n.configuration['Caption'] is not None:
                            try:
                                caption = n.configuration['Caption']
                            except:
                                caption = " "
                        else:
                            caption = " "
                        fill = n.configuration['Style']['@FillColor']
                        border = n.configuration['Style']['@BorderColor']
                        capFill = n.configuration['Style']['@TextColor']
                        disabled = n.configuration['Disabled']['@value']
                        folded = n.configuration['Folded']['@value']
                        if disabled == "True":
                            caption += " (Container is Disabled)"
                        if folded == "True":
                            caption += " (container is Minimized)"

                        self.d.rectangle([n.positionX,n.positionY,n.max_X,n.max_Y],fill=fill,outline=border)
                        captionX = int(((n.positionX + n.max_X) / 2) - len(caption)*2)
                        captionY = n.positionY+3
                        self.d.text([captionX,captionY],caption,fill=capFill)

                    #TEXT BOX
                    elif 'TextBox' == n.nodeType:
                        padding = 0

                        if '@name' in n.configuration['FillColor'].keys():
                            fillcolor = n.configuration['FillColor']['@name']
                        else:
                            r = int(n.configuration['FillColor']['@r'])
                            g = int(n.configuration['FillColor']['@g']) 
                            b = int(n.configuration['FillColor']['@b'])
                            fillcolor = (r,g,b)

                        if n.configuration['Shape']['@shape']=='3':
                                # Transparent, do not add rectangle
                                pass
                        else:
                            #add 0 pixels to comment y position, there seems to be some sort of padding build into alteryx
                            #Alteryx font is smaller for some reason, so we will add a little bit extra room in x and y for comments
                            self.rounded_rectangle(self.d,[(n.positionX,n.positionY+padding),(int(n.max_X+10),int(n.max_Y + 10))],5,fill=fillcolor,outline=(24,24,24))
                            #rounded_rectangle(d,[(n.positionX,n.positionY),(int(n.max_X +n.width*.1),int(n.max_Y+n.height*.3))],5,fill=fillcolor,outline=(24,24,24))
                            #d.rectangle([n.positionX,n.positionY,int(n.max_X +n.width*.1),int(n.max_Y+n.height*.3)],fill=fillcolor,outline=(24,24,24))
                        
                        if n.configuration["Text"] is not None:
                            caption =  n.configuration['Text']
                            if '@name' in n.configuration['TextColor']:
                                textColor = n.configuration['TextColor']['@name']
                            else:
                                r = int(n.configuration['TextColor']['@r'])
                                g = int(n.configuration['TextColor']['@g']) 
                                b = int(n.configuration['TextColor']['@b'])
                                textColor = (r,g,b)
                            captionX = int(n.positionX) + 5 #int(((n.positionX + n.max_X) / 2))  # - len(caption)*2)
                            captionY = n.positionY#+3

                            text = self.wrapText(caption, n.width/7)
                            try:    
                                self.d.text([captionX,captionY+padding],text,fill=textColor)  
                            except Exception as e:
                                try:
                                    #Try purging all characters that might break the Latin-1 encoding
                                    text = re.sub(r'[^a-zA-Z\s\"\n\r\.\,\d]+', '', text)
                                    self.d.text([captionX,captionY+padding],text,fill=textColor)  
                                    print("Handled text parsing Error",e.args)
                                except Exception as e1:
                                    print("\nUnhandled text parsing Error:",e1.args,"\n")

                    else:
                        nodeHeight=36
                        nodeWidth=42
                        
                        if n.nodeType in self.imLib.keys():
                            self.img.paste(self.imLib[n.nodeType],(int(n.positionX),int(n.positionY)),mask=self.imLib[n.nodeType])
                        else:
                            self.d.rectangle([n.positionX,n.positionY,int(n.positionX+nodeWidth),int(n.positionY+nodeHeight)],fill='Grey',outline='Black')
                        #Image Text
                        if n.annotations is not None:
                            if len(n.annotations)>5:
                                noteText = self.wrapText(n.annotations,15)
                            else:
                                noteText = n.annotations
                        else:
                            noteText = ""

                        if noteText.startswith("\n") and len(noteText)>2:
                            noteText=noteText[1:]

                        self.d.text([n.positionX, n.positionY+nodeHeight],
                        "({0}) - {1}\n{2}".format(n.nodeId,n.nodeType,noteText),
                            fill='Black') 
                    #otherwise just draw a placeholder for now

        # Now we draw connections
        for c in self.connections:
            col = (0,0,0)
            if c.isWireless:
                col = (166,166,166)
            #d.line(c.getCoords(),fill=col,width=1)
            self.drawCurvyLine(self.d,c.getCoords(),fill=col,width=1)

            self.img.paste(self.imLib['input'],(int(c.getCoords()[2]-10),int(c.getCoords()[3]-5)),mask=self.imLib['input'])
            self.img.paste(self.imLib['output'],(int(c.getCoords()[0]),int(c.getCoords()[1]-5)),mask=self.imLib['output'])

        if alteryxEnv:
            #TODO: write the file path to image into a dataframe: outpath+'Canvas.png'
            pass
        self.img.save(outpath+'Canvas.png')
        if alteryxEnv:
            data = {'Record':[1], 'Path':[outpath+'Canvas.png']} 
            Alteryx.write(pd.DataFrame(data),3)
        return self


    def drawSubflows(self, inpath):
        #Step 1, get image and subflows
        imagepath = inpath+'Canvas.png'
        try:
            fullImg = Image.open(imagepath)
            #subflows = self.getSubflows()
            subflows = self.getSubflowsByContiner()
            
            #Step 2, Get unique list of subflows
            subflowIDs = subflows['subFlowId'].unique()
            for sid in subflowIDs:
                nodes = subflows[subflows['subFlowId'] == sid]['nodeId'].tolist()
                subflowNodes = []
                for n in nodes:
                    subflowNodes.append(self.getNodeById(n))

                #Get bounding box for nodes in list
                x1 = -1 #min position x
                y1 = -1 #min position y
                x2 = -1 #max position x
                y2 = -1 #max position y

                for node in subflowNodes:
                    if node.positionX < x1 or x1==-1:
                        x1 = node.positionX 
                    if node.positionX > x2 or x2==-1:
                        x2 = node.positionX
                    if node.positionY < y1 or y1==-1:
                        y1 = node.positionY
                    if node.positionY > y2 or y2==-1:
                        y2 = node.positionY

                #nodes are 42x36
                cropbuffer = 100
                x1 -= cropbuffer
                y1 -= cropbuffer/2
                x2 += cropbuffer+42
                y2 += cropbuffer/2+36

                #set a min width, unless it hits the edge of the image
                if x2 - x1 < 400:
                    split = 400 - (x2-x1)
                    x1-= split/2
                    x2+= split/2

                x1 = int(max(x1,0))
                y1 = int(max(y1,0))
                x2 = int(min(x2,fullImg.size[0]))
                y2 = int(min(y2,fullImg.size[1]))

                #print("Bounding Box for {0} : ".format(sid), x1, y1, x2, y2)
                fullImg.crop((x1,y1,x2,y2)).save(inpath+'Canvas'+'_'+str(sid)+'.png')

                


        except Exception as ex:
            print("Image or Subflows missing", ex.args)

        return self

    def writeObjects(self, outpath):
        if self.doc["AlteryxDocument"]["Nodes"] is not None:
            self.objects = pd.DataFrame([n.__dict__ for n in self.nodes])
            self.objects = self.objects[['nodeId','nodeType','fields','tables','isDisabled','formulas','configuration','annotations','metaInfo','positionX','positionY','width','height','max_X','max_Y','isChild','text']]
            
        try:
            self.order = pd.DataFrame(self.getOrder(self.nodes,self.connections), columns=["nodeId"] )
            
            self.order['Order'] = self.order.index
            self.result = pd.merge(self.objects, self.order, how='left', on=['nodeId']).sort_values(by=['Order'])
            self.result = pd.merge(self.result, self.getSubflowsByContiner(), how='left', on=['nodeId']).sort_values(by=['subFlowId','Order'])
            
            self.result['nextNodes'] = self.result['nodeId'].apply(lambda x: str(self.getNextNodesFromCurrentId([x])).replace("[","").replace("]","").replace("'",""))
            self.result['formulas'] = self.result['formulas'].apply(lambda x: str(x).replace("'",""))
            self.result['fields'] = self.result['fields'].apply(lambda x: str(x).replace("'",""))
            self.result['tables'] = self.result['tables'].apply(lambda x: str(x).replace("'",""))
            self.result['configuration'] = self.result['configuration'].apply(lambda x: str(x))
            self.result['annotations'] = self.result['annotations'].apply(lambda x: str(x))
            self.result['metaInfo'] = self.result['metaInfo'].apply(lambda x: str(x))
            
            #Just get the columns we want here 
            self.result = self.result[['Order','subFlowId','nodeId','nextNodes','nodeType','isDisabled','formulas','fields','tables','configuration','annotations','metaInfo','isChild','text']]
            for column in self.result:
                if self.result[column].dtypes == 'object': 
                    if column == "metaInfo":
                        #print(self.result[column].apply(lambda x: str(x).replace("\\n","").replace("\"","").replace("\\r","")))
                        self.result[column] = self.result[column].apply(lambda x: str(x).replace("\\n","").replace("\\r",""))
                    #pass
                    #here we have to purge special characters

            if alteryxEnv:
                Alteryx.write(self.result,1)

            self.result.to_csv(outpath+"Objects.csv",index=False)
            

        except Exception as e:
            print("Could not prepare dataframe for nodes\n{0}".format(e))
            if alteryxEnv:
                try:
                    Alteryx.write(self.objects,1) 
                except Exception as f:
                    print("Could not prepare dataframe for Alteryx\n{0}".format(f))

            self.objects.to_csv(outpath+"Objects.csv",index=False)


        if self.doc["AlteryxDocument"]["Connections"] is not None:
            self.cons = pd.DataFrame([n.__dict__ for n in self.connections])
            self.cons = self.cons[['connectionName','originNodeId','destinationNodeId','isWireless','originConnection','destinationConnection','destinationNode','originNode']].drop(['destinationNode','originNode'],axis=1)
            
            if alteryxEnv:
                Alteryx.write(self.cons,2)

            self.cons.to_csv(outpath+"Connections.csv",index=False)

        return self

    def generateSummary(self, outpath):
        try:
            # Prepara os dados do fluxo para o Prompt
            workflow_name = os.path.basename(self.filePath)
            tools_data = []
            for node in self.nodes:
                if node.nodeType not in ['ToolContainer', 'TextBox', 'Tab', 'Label', 'LabelGroup']:
                    tool_info = f"ID: {node.nodeId} | Tipo: {node.nodeType}"
                    if node.nodeType == 'Formula' and len(node.formulas) > 0:
                        tool_info += f" | Fórmulas: {', '.join([str(f) for f in node.formulas if f])}"
                    if node.nodeType in ['DbFileInput', 'DbFileOutput'] and len(node.tables) > 0:
                        tool_info += f" | Arquivo/Tabela: {', '.join(node.tables)}"
                    tools_data.append(tool_info)
            
            prompt = f"""
            Você é um Engenheiro de Dados especialista em Alteryx. 
            Estou te enviando as ferramentas extraídas de um fluxo chamado '{workflow_name}'.
            Interpretando os tipos de ferramentas, fórmulas e arquivos de entrada/saída, escreva um relatório PROFISSIONAL, 
            FLUIDO e CLARO em Português do Brasil explicando o que esse fluxo provavelmente faz.
            Não liste apenas as ferramentas, explique o objetivo de negócio e a jornada do dado (de onde vem, o que é transformado e para onde vai).
            
            Dados extraídos das ferramentas:
            {chr(10).join(tools_data)}
            """
            
            summary_text = f"Resumo Analítico do Fluxo Alteryx: {workflow_name}\n"
            summary_text += "=" * 60 + "\n\n"
            
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel
                
                # Assume default application credentials initialized via gcloud init
                # Explicitly trying us-central1 or let ADC handle project
                vertexai.init(location="us-central1") 
                
                # Using gemini-1.0-pro since gemini-1.5 threw a 404 error
                model = GenerativeModel("gemini-2.5-flash")
                response = model.generate_content(prompt)
                
                summary_text += response.text
                
            except Exception as ai_err:
                summary_text += "[AVISO: Não foi possível conectar ao Google Cloud Vertex AI para gerar o resumo interpretativo.]\n"
                summary_text += f"[Detalhes do Erro: {ai_err}]\n\n"
                summary_text += "Resumo Básico das Ferramentas:\n"
                summary_text += "\n".join(tools_data)
            
            summary_file_path = os.path.join(outpath, "Resumo_Fluxo.txt")
            with open(summary_file_path, "w", encoding="utf-8") as f:
                f.write(summary_text)
                
            print(f"Resumo gerado em: {summary_file_path}")
            return self
        except Exception as e:
            print(f"Erro ao preparar dados para o resumo: {e}")
            return self

def buildReport(file, outBasePath, recusive=False):
    thisPath = outBasePath+os.path.basename(file)+".report\\"
    if not os.path.exists(os.path.abspath(thisPath)):
        os.makedirs(os.path.abspath(thisPath))
    #print("Writing {0} to {1}".format(file,thisPath))
    #Get base path of imager utility
    mapPath = os.path.dirname(os.path.dirname(os.path.abspath(outBasePath)))+"/appdata/config/imageMapping.json"
    Workflow(file).parseWorkflow(mapPath).drawWorkflow(thisPath).writeObjects(thisPath).drawSubflows(thisPath).generateSummary(thisPath)



if alteryxEnv: #Alteryx Environment
    config = Alteryx.read("#1")
    readFile = config['Path'][0]
    # this gets the current worknig directory of the Alteryx documentor that called this script
    wkdir = config['wkdir'][0]
    #namePath = config['namePath'][0]

    #This causes a bug in Alteryx
    #os.chdir(wkdir)

    # Set the output path to wkdir, use dirname to go up one path, then go to the outputs subfolder
    outpath = os.path.dirname(os.path.abspath(wkdir))+"\\outputs\\"
    buildReport(readFile, outpath)
else: 
    if __name__ == "__main__":
        #This is a test path for non alteryx env#
        wkdir = "C:\\Users\\adilsonss\\OneDrive - Suzano S A\\PrintSap\\Notebok\\alteryx_doc\\Alteryx_Auto_Documenter_Functional"
        os.chdir(wkdir)
        outpath = os.getcwd()+"\\outputs\\"

        import os
        filelist = []
        filelist.append("C:\\Users\\adilsonss\\OneDrive - Suzano S A\\PrintSap\\Notebok\\alteryx_doc\\Alteryx_Auto_Documenter_Functional\\Image Workflow.yxwz")

        if debug:
            for f in filelist:
                buildReport(f, outpath)
        # Use ThreadPoolExecutor to do mass processing
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()*2) as executor:
                executor.map(lambda f: buildReport(f, outpath), filelist)

