import concurrent
import random
import socket
import sys
import threading


import grpc
from concurrent import futures
import time
import raft_pb2, raft_pb2_grpc
import os
from raftNode import Node,NodeList
port = sys.argv[1]
ip = socket.gethostbyname(socket.gethostname())

leader = False

node:Node = Node(nodeId="-1",ip="-1",port="-1")


def setValue(key,value):
   readItr = open("data.txt","r")
   writeItr = open("data.txt","w")
   
   entries = readItr.readlines()
   for entry in entries:
       if entry.split(" ")[0] == key:
           writeItr.write(key+" "+value+"\n")
       else:
           writeItr.write(entry)
   writeItr.close()
   readItr.close()
   return ""
   
def getValue(key):
    readItr = open("data.txt","r")
    entries = readItr.readlines()
    for entry in entries:
        if(entry.split(" ")[0] == key):
            readItr.close()
            return entry.split(" ")[1]
    readItr.close()  
    return ""

def noOp():
    writeItr = open("data.txt","a")
    writeItr.write("No-Op+\n")
    writeItr.close()
    return ""

def ReplicateLogs(req):
    prefix = node.sentLength[req[0]]
    suffix = node.log[prefix:]
    prefixTerm=0
    if prefix>0:
        prefixTerm=node.log[prefix-1].term

    for j,i in NodeList.items():
        with grpc.insecure_channel(i) as channel:
            stub = raft_pb2_grpc.RaftStub(channel)
            req = raft_pb2.ReplicateLogArgs()
            res = stub.ReplicateLogRequest(req)


def timeout():
    time_rand = time.time() + random.uniform(1, 2)
    while True:
        if time.time() >= time_rand:
            return True




def StartElection():

    votes = 0
    for j,i in NodeList.items():
        if i==node.ipAddr+node.port:
            continue
        with grpc.insecure_channel(i) as channel:
            stub = raft_pb2_grpc.RaftStub(channel)
            request = raft_pb2.RequestVotesArgs(term=1,candidateId=j,lastLogTerm=0,lastLogIndex=0)
            response = stub.RequestVote(request)
            if (response.voteGranted == True and node.currentRole=="Candidate" and node.currentTerm==response.term):
                node.votesReceived.append(response.NodeId)

    if (len(node.votesReceived) >= len(NodeList) / 2):
        node.currentRole = "Leader"
        node.currentLeader = node.nodeId
        # TODO: Need to think how to get the ip address of followers: One way is to assume every node sent it. which is done below
        for j,i in NodeList.items():
            if i == Node.ipAddr + Node.port:
                continue
            # with grpc.insecure_channel(i) as channel:
            #     stub = raft_pb2_grpc.RaftStub(channel)
                # Replicating logs

            queryNode = NodeList[j] # ! Replace i with node id
            prefixLen = queryNode.sentLength
            suffix = []
            for entryInd in range(prefixLen,len(node.log)):
                logEntry = node.log[entryInd]
                suffix.append(raft_pb2.entry(index=logEntry.index,term=logEntry.term,key=logEntry.key,val=logEntry.val))

            # request = raft_pb2.AppendEntriesArgs()
            req = raft_pb2.ReplicateLogArgs(leaderId=node.nodeId,currentTerm=node.currentTerm,prefixLen=prefixLen,prefixTerm=node.log[prefixLen-1].term,commitLength=node.commitLength,suffix=suffix)
            # TODO: Fill these
            req1= [node.nodeId,NodeList[node.nodeId],j,i]
            res = ReplicateLogs(req1)

    else:
        if response.term>node.currentTerm:
            node.currentTerm=response.term
            node.currentRole="Follower"
            node.votedFor=None


def SendBroadcast(msg):
    if node.currentRole == "Leader":
        node.log.append(msg)
        node.ackedLength[node.nodeId] = len(node.log)
        for j,i in NodeList.items():
            if i == Node.ipAddr + Node.port:
                continue
                # Replicating logs

            queryNode = NodeList[j]  # ! Replace i with node id
            prefixLen = queryNode.sentLength
            suffix = []
            for entryInd in range(prefixLen, len(node.log)):
                logEntry = node.log[entryInd]
                suffix.append(raft_pb2.entry(index=logEntry.index, term=logEntry.term, key=logEntry.key,
                                             val=logEntry.val))

            # request = raft_pb2.AppendEntriesArgs()
            req = raft_pb2.ReplicateLogArgs(leaderId=node.nodeId, currentTerm=node.currentTerm,
                                            prefixLen=prefixLen, prefixTerm=node.log[prefixLen - 1].term,
                                            commitLength=node.commitLength, suffix=suffix)
            req1= [node.nodeId,NodeList[node.nodeId],j,i]
            res = ReplicateLogs(req1)
    else:
        # Send to leader via FIFO link? No idea
        # ? Should the nodes pass the client message to leader normally ?
        pass


def SuspectFail():
    pass



class RaftServicer(raft_pb2_grpc.RaftServicer):


    def AppendEntries(self, request, context):
        print(request.term)
        # return super().AppendEntries(request, context)

    def RequestVote(self, request, context):
        vote = True
        if(request.term > node.currentTerm):
            node.currentTerm = request.term
            node.currentRole="Follower"
            node.votedFor=None
        node.lastTerm=0
        if len(node.log)>0:
            node.lastTerm = node.log[len(node.log)-1].term
        ok = (request.lastLogTerm > node.lastTerm) or (request.lastLogTerm==node.lastTerm and request.lastLogIndex >= len(node.log))

        if request.term == node.currentTerm and ok and node.votedFor==None:
            node.votedFor = request.candidateId
            vote=True
        else:
            vote=False

        return raft_pb2.RequestVotesRes(term=1,voteGranted=vote,longestDurationRem=0)



    def ServeClient(self, request, context):
        request = request.split(" ")
        operation = request[0]
        data = ""
        # ! Pass the message to leader
        # TODO
        if(node.nodeId != node.leaderId):

            return raft_pb2.ServeClientReply(Data=data,LeaderID=node.leaderId,Success=False)
        if(operation == "SET"):
            key = request[1]
            value = request[2]
            data = setValue(key,value)
        elif(operation == "GET"):
            key = request[1]
            data = getValue(key)
        else:
            data = noOp()
        return raft_pb2.ServeClientReply(Data=data,LeaderID=node.leaderId,Success=True)
        # print(request.request)
        # return super().ServeClient(request, context)
    def ReplicateLogRequest(self,request,context):
        # if(request.term > )
        # TODO implement this functionality
        if request.term>node.currentTerm:
            node.currentTerm=request.term
            node.votedFor=None
            #Cancel Election
        if request.term==node.currentTerm:
            node.currentRole="Follower"
            node.currentLeader=request.leaderId
        ok= (len(node.log)>=request.prefixLen) or (request.prefixLen==0 and node.log[request.prefixLen-1].term==request.prefixTerm)
        if node.currentTerm==request.term and ok:
            #Append Entries
            ack = request.prefixLen+len(request.suffix)
            with grpc.insecure_channel(NodeList[node.leaderId]) as channel:
                stub = raft_pb2_grpc.RaftStub(channel)
                req = raft_pb2.ReplicateLogResponseArgs(node.nodeId,node.currentTerm,ack,True)
                res = stub.ReplicateLogRespone(req)
            #Send Ack to leader of success
        else:
            #Send Ack to leader of failure
            with grpc.insecure_channel(NodeList[node.leaderId]) as channel:
                stub = raft_pb2_grpc.RaftStub(channel)
                req = raft_pb2.ReplicateLogResponseArgs(node.nodeId, node.currentTerm, 0, False)
                res = stub.ReplicateLogRespone(req)
    def ReplicateLogResponse(self, request, context):
        if node.currentTerm == request.followerterm and node.currentRole=="Leader":
            if request.success==True and request.ack >= node.ackedLength[request.followerId]:
                node.sentLength[request.followerId] = request.ack
                node.ackedLength[request.followerId] = request.ack
                #Commit Log
                req = raft_pb2.CommitEntriesArgs()
                res=self.CommitEntries(req,context)
            elif node.sentLength[request.followerId] > 0 :
                node.sentLength[request.followerId] -=1
                #Replicate Log
        elif request.followerterm > node.currentTerm:
            node.currentTerm=request.followerterm
            node.currentRole = "Follower"
            node.votedFor = None
            #Cancel Election
    def CommitEntries(self,context):
        minacks = (len(NodeList)+1)/2
        ready=[]
        # TODO: Didnt get this
        for i in range(1,len(node.log)):
            ready.append(0)
        if ready!=[] and max(ready)>node.commitLength and node.log[max(ready)-1].term==node.currentTerm:
            for i in range(node.commitLength,max(ready)):
                #Deliver Log message to application
                continue
            node.commitLength=max(ready)







def serve():
    global node

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
    raft_pb2_grpc.add_RaftServicer_to_server( RaftServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    n = int(input("Enter Node ID : "))

    try:
        if(os.path.isdir(f"logs_node_{n}")):
            #take data from log files
            path = os.getcwd() + f"/logs_node_{n}/"
            f = open(path + f"logs.txt", "a+")
            f1 = open(path + "metadata.txt", "a+")
            f2 = open(path + "dump.txt", "a+")
            #For now
            node = Node(nodeId=n, ip=ip, port=port)

        else:
            node = Node(nodeId=n, ip = ip, port=port)
            os.mkdir(f"logs_node_{n}", 0o777)
            path = os.getcwd() + f"/logs_node_{n}/"
            f = open(path + f"logs.txt", "a+")
            f1 = open(path + "metadata.txt", "a+")
            f2 = open(path + "dump.txt", "a+")

        if SuspectFail() or timeout():
            node.currentTerm+=1
            node.votedFor = node.nodeId
            node.votesReceived.append(node.nodeId)
            node.currentRole="Candidate"
            node.lastTerm=0
            if len(node.log)>0:
                node.lastTerm = node.log[len(node.log)-1].term
            StartElection()



    except FileExistsError:
        pass

    try:
        while True:
            time.sleep(3600)  # One hour
    except KeyboardInterrupt:
        server.stop(0)

t=[]
if __name__ == '__main__':

    th1 = threading.Thread(target=serve)
    th2 = threading.Thread(target=timeout)
    t.append(th1)
    t.append(th2)
    try:
        for i in t:
            i.start()
        for i in t:
            i.join()

    except:
        sys.exit(0)


