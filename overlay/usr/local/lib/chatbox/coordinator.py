#!/usr/bin/env python3
"""Local, stateless model coordinator. No model downloads or remote endpoints."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import http.client
import http.server
import ipaddress
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit
import uuid

MAX_BODY=65536
MAX_REPLY=1048576

def event(**fields):
    print(json.dumps(fields,separators=(',',':')),flush=True)

@dataclass(frozen=True)
class Backend:
    name: str
    base_url: str
    model: str

@dataclass(frozen=True)
class Config:
    backend: str | None
    backends: dict
    fallbacks: tuple=()
    timeout_seconds: float=20
    max_tokens: int=128


def load_config(path):
    raw=Path(path).read_bytes()
    if len(raw)>MAX_BODY:raise ValueError('Configuration is too large')
    data=json.loads(raw)
    if not isinstance(data,dict) or set(data)-{'backend','backends','fallbacks','timeout_seconds','max_tokens'}:
        raise ValueError('Unknown configuration fields')
    if not isinstance(data.get('backends',{}),dict):raise ValueError('backends must be an object')
    profiles={}
    for name,item in data.get('backends',{}).items():
        if not isinstance(name,str) or not name or not isinstance(item,dict) or set(item)!={'base_url','model'}:
            raise ValueError('Each backend needs a name, base_url and model')
        if not isinstance(item['base_url'],str):raise ValueError('base_url must be text')
        url=urlsplit(item['base_url'])
        try:local=ipaddress.ip_address(url.hostname).is_loopback
        except (ValueError,TypeError):local=False
        if not local or url.scheme!='http' or url.username or url.password or url.query or url.fragment or url.path.rstrip('/')!='/v1':
            raise ValueError('Backend URL must be numeric HTTP loopback with /v1 path')
        if url.port is not None and not 1<=url.port<=65535:raise ValueError('Invalid backend port')
        if not isinstance(item['model'],str) or not item['model'].strip() or len(item['model'])>256:
            raise ValueError('Backend model must be explicit')
        profiles[name]=Backend(name,item['base_url'].rstrip('/'),item['model'])
    selected=data.get('backend')
    fallbacks=data.get('fallbacks',[])
    if selected is not None and not isinstance(selected,str):raise ValueError('backend must be a name or null')
    if not isinstance(fallbacks,list) or not all(isinstance(x,str) for x in fallbacks) or len(set(fallbacks))!=len(fallbacks):raise ValueError('Fallbacks must be unique backend names')
    if selected is not None and selected not in profiles:raise ValueError('Selected backend is not configured')
    if any(x not in profiles or x==selected for x in fallbacks):raise ValueError('Invalid fallback backend')
    if selected is None and fallbacks:raise ValueError('Fallbacks need a selected backend')
    timeout=data.get('timeout_seconds',20);tokens=data.get('max_tokens',128)
    if type(timeout) not in (int,float) or not 1<=timeout<=60:raise ValueError('Timeout must be 1..60 seconds')
    if type(tokens) is not int or not 1<=tokens<=512:raise ValueError('max_tokens must be 1..512')
    return Config(selected,profiles,tuple(fallbacks),timeout,tokens)


class Deadline:
    def __init__(self,seconds):self.end=time.monotonic()+seconds
    def remaining(self):
        left=self.end-time.monotonic()
        if left<=0:raise TimeoutError('deadline')
        return left


def shutdown(sock):
    try:sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass


@contextmanager
def upstream(backend,path,payload,deadline):
    url=urlsplit(backend.base_url)
    connection=http.client.HTTPConnection(url.hostname,url.port or 80,timeout=deadline.remaining())
    timer=None;response=None
    try:
        connection.connect()
        sock=connection.sock
        # A wall-clock watchdog also stops slow-drip responses; a socket read
        # timeout alone is only an inactivity timeout, not a total turn budget.
        timer=threading.Timer(deadline.remaining(),shutdown,args=(sock,));timer.daemon=True;timer.start()
        connection.request('GET' if payload is None else 'POST',url.path+path,
                           body=None if payload is None else json.dumps(payload).encode(),
                           headers={'Content-Type':'application/json','Connection':'close'})
        response=connection.getresponse()
        yield response
    finally:
        if timer:timer.cancel()
        if response:response.close()
        connection.close()


def read_limited(response,deadline,on_first=None):
    data=bytearray()
    while True:
        deadline.remaining()
        chunk=response.read1(min(65536,MAX_REPLY+1-len(data)))
        if not chunk:break
        if not data and on_first:on_first()
        data.extend(chunk)
        if len(data)>MAX_REPLY:raise ValueError('upstream_reply_too_large')
    return bytes(data)


def readiness(config,backend=None,deadline=None):
    if config.backend is None:return {'state':'unconfigured','ready':False,'backend':None}
    backend=backend or config.backends[config.backend]
    start=time.monotonic();result={'state':'loading','ready':False,'backend':backend.name,'model':backend.model}
    deadline=deadline or Deadline(2)
    try:
        with upstream(backend,'/models',None,deadline) as response:
            if response.status!=200:raise ValueError('backend_not_ready')
            data=json.loads(read_limited(response,deadline))
            if not any(isinstance(x,dict) and x.get('id')==backend.model for x in data.get('data',[])):
                raise ValueError('model_not_advertised')
        result.update(state='ready',ready=True)
    except (OSError,http.client.HTTPException,ValueError,TypeError,AttributeError) as error:
        result['error']='deadline' if isinstance(error,TimeoutError) else type(error).__name__
    result['probe_ms']=round((time.monotonic()-start)*1000,1)
    return result


def diagnostics(root=Path('/sys'),proc=Path('/proc')):
    def text(path):
        try:return path.read_text()[:1024].strip()
        except (OSError,UnicodeError):return None
    cpu=[]
    for policy in sorted((root/'devices/system/cpu/cpufreq').glob('policy*')):
        cpu.append({'policy':policy.name,'cpus':text(policy/'affected_cpus'),
                    'governor':text(policy/'scaling_governor'),'frequency_khz':text(policy/'scaling_cur_freq')})
    clocks=[]
    for device in sorted((root/'class/devfreq').glob('*')):
        clocks.append({'device':device.name,'governor':text(device/'governor'),'frequency_hz':text(device/'cur_freq')})
    thermal=[]
    for zone in sorted((root/'class/thermal').glob('thermal_zone*')):
        thermal.append({'type':text(zone/'type'),'temperature_millicelsius':text(zone/'temp')})
    memory={}
    for line in (text(proc/'meminfo') or '').splitlines():
        key,_,value=line.partition(':')
        if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):memory[key]=value.strip()
    return {'cpu':cpu,'devfreq':clocks,'thermal':thermal,'memory':memory,
            'thp':text(root/'kernel/mm/transparent_hugepage/enabled')}


def messages_from(data):
    messages=data.get('messages')
    if not isinstance(messages,list) or not 1<=len(messages)<=32:raise ValueError('Supply 1..32 messages')
    result=[]
    for message in messages:
        if not isinstance(message,dict) or message.get('role') not in ('system','user','assistant') or not isinstance(message.get('content'),str):
            raise ValueError('Invalid text message')
        result.append({'role':message['role'],'content':message['content']})
    if type(data.get('stream',False)) is not bool:raise ValueError('stream must be boolean')
    return result


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    def log_message(self,*args):pass  # Never log prompts, audio or response bodies.
    def reply(self,status,data):
        body=json.dumps(data,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/health':self.reply(200,{'ok':True,'configured':self.server.config.backend is not None})
        elif self.path=='/ready':
            result=readiness(self.server.config);self.reply(200 if result['ready'] else 503,result)
        elif self.path=='/diagnostics':self.reply(200,diagnostics())
        else:self.reply(404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/v1/chat/completions':self.reply(404,{'error':'not_found'});return
        try:
            if self.headers.get('Transfer-Encoding'):raise ValueError('Chunked requests are not accepted')
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=MAX_BODY:raise ValueError('Request must be 1..65536 bytes')
            data=json.loads(self.rfile.read(length));messages=messages_from(data)
        except (ValueError,TypeError,AttributeError):self.reply(400,{'error':'invalid_request'});return
        config=self.server.config
        if config.backend is None:self.reply(503,{'error':'unconfigured'});return
        if not self.server.inference.acquire(blocking=False):self.reply(429,{'error':'busy'});return
        request_id=uuid.uuid4().hex;started=time.monotonic();committed=False;headers_sent=False
        deadline=Deadline(config.timeout_seconds);last='backend_unavailable';used=None;first_byte=None;ok=False;attempts=[]
        def mark_first():
            nonlocal first_byte
            if first_byte is None:first_byte=round((time.monotonic()-started)*1000,1)
        try:
            for name in (config.backend,*config.fallbacks):
                backend=config.backends[name];used=name
                probe=readiness(config,backend,deadline)
                attempt={'backend':name,'probe_ms':probe.get('probe_ms',0),'ready':probe['ready']};attempts.append(attempt)
                if not probe['ready']:last='backend_not_ready';continue
                payload={'model':backend.model,'messages':messages,'max_tokens':config.max_tokens,'stream':data.get('stream',False)}
                try:
                    call_started=time.monotonic()
                    with upstream(backend,'/chat/completions',payload,deadline) as response:
                        attempt['headers_ms']=round((time.monotonic()-call_started)*1000,1);attempt['http_status']=response.status
                        if response.status!=200:last='backend_http_'+str(response.status);continue
                        # Once a backend accepts a request, do not silently retry
                        # it on another model after partial output or a timeout.
                        committed=True
                        if payload['stream']:
                            if not response.getheader('Content-Type','').lower().startswith('text/event-stream'):
                                raise ValueError('invalid_stream_type')
                            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();headers_sent=True
                            total=0;pending=b'';done=False
                            while True:
                                deadline.remaining();chunk=response.read1(4096)
                                if not chunk:break
                                total+=len(chunk)
                                if total>MAX_REPLY:raise ValueError('upstream_reply_too_large')
                                mark_first()
                                self.wfile.write(chunk);self.wfile.flush()
                                pending+=chunk
                                lines=pending.split(b'\n');pending=lines.pop()
                                if any(line.startswith(b'data:') and line[5:].strip()==b'[DONE]' for line in lines):
                                    done=True;break
                            if not done:raise ValueError('incomplete_stream')
                        else:
                            body=read_limited(response,deadline,mark_first);answer=json.loads(body)
                            # Validate a minimal OpenAI text reply before returning.
                            if not isinstance(answer['choices'][0]['message']['content'],str):raise ValueError('invalid_reply')
                            self.reply(200,answer)
                        ok=True;break
                except (OSError,http.client.HTTPException,ValueError,TypeError,KeyError,IndexError):
                    last='backend_request_failed'
                    if committed:break
            if not ok and not committed:self.reply(504 if time.monotonic()>=deadline.end else 503,{'error':last})
            elif not ok and committed and payload['stream'] and headers_sent:
                self.wfile.write(b'event: error\ndata: {"error":"backend_request_failed"}\n\n');self.wfile.flush()
            elif not ok and committed:self.reply(504 if time.monotonic()>=deadline.end else 502,{'error':last})
        except (OSError,http.client.HTTPException):pass
        finally:
            try:
                event(event='llm_request',request_id=request_id,backend=used,ok=ok,
                      total_ms=round((time.monotonic()-started)*1000,1),first_byte_ms=first_byte,attempts=attempts,error=None if ok else last)
            finally:
                self.server.inference.release()


class LocalServer(http.server.ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,config):
        if not ipaddress.ip_address(address[0]).is_loopback:raise ValueError('Coordinator must bind to loopback')
        self.config=config;self.inference=threading.Lock();self.slots=threading.BoundedSemaphore(8)
        super().__init__(address,Handler)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        timer=threading.Timer(self.config.timeout_seconds+5,shutdown,args=(request,));timer.daemon=True;timer.start()
        request.settimeout(5)
        try:super().process_request_thread(request,address)
        finally:timer.cancel();self.slots.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,default=Path('/etc/chatbox/app.json'))
    args=parser.parse_args();config=load_config(args.config)
    event(event='coordinator_start',backend=config.backend,state='unconfigured' if config.backend is None else 'loading')
    with LocalServer(('127.0.0.1',8088),config) as server:server.serve_forever()

if __name__=='__main__':main()
