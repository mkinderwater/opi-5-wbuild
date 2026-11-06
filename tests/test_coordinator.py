from contextlib import contextmanager,redirect_stdout
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'overlay/usr/local/lib/chatbox'))
import coordinator as app

class EngineHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,data):
        body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        self.reply(200,{'data':[{'id':self.server.model}]} if self.server.mode!='loading' else {'data':[]})
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.calls.append(data);self.server.entered.set()
        mode=self.server.mode
        try:
            if mode=='fail':self.reply(503,{'error':'not_ready'});return
            if mode=='hold':self.server.release.wait(2)
            if mode=='invalid':self.reply(200,{'unexpected':True});return
            if mode in ('stream','truncated-stream'):
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n');self.wfile.flush()
                if mode=='truncated-stream':return
                self.server.release.wait(2)
                self.wfile.write(b'data: {"choices":[],"usage":{}}\n\ndata: [DONE]\n\n');self.wfile.flush();return
            if mode=='drip':
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                for _ in range(30):self.wfile.write(b' ');self.wfile.flush();time.sleep(.05)
                return
            self.reply(200,{'choices':[{'message':{'role':'assistant','content':'answer'}}]})
        except OSError:pass

@contextmanager
def engine(model='model',mode='ok'):
    server=ThreadingHTTPServer(('127.0.0.1',0),EngineHandler);server.daemon_threads=True
    server.model=model;server.mode=mode;server.calls=[];server.entered=threading.Event();server.release=threading.Event()
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield server
    finally:server.release.set();server.shutdown();server.server_close();thread.join()

@contextmanager
def gateway(config):
    server=app.LocalServer(('127.0.0.1',0),config)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield server
    finally:server.shutdown();server.server_close();thread.join()

def profile(name,server,model=None):return app.Backend(name,'http://127.0.0.1:'+str(server.server_port)+'/v1',model or server.model)
def request(server,path,body=None):
    c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=4)
    c.request('GET' if body is None else 'POST',path,body=None if body is None else json.dumps(body),headers={'Content-Type':'application/json'})
    response=c.getresponse();data=response.read();status=response.status;c.close()
    return status,json.loads(data)
PROMPT={'messages':[{'role':'user','content':'private spoken phrase'}]}

class ConfigTests(unittest.TestCase):
    def load(self,data):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'app.json';p.write_text(json.dumps(data));return app.load_config(p)
    def test_unconfigured_default_is_valid(self):
        c=app.load_config(ROOT/'overlay/etc/chatbox/app.json');self.assertIsNone(c.backend);self.assertEqual(c.fallbacks,())
    def test_only_numeric_loopback_backend_urls_are_allowed(self):
        for url in ['http://192.168.24.134/v1','https://127.0.0.1/v1','http://localhost/v1','http://127.0.0.1/v1?x=1','http://user:pass@127.0.0.1/v1']:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):self.load({'backend':'a','backends':{'a':{'base_url':url,'model':'m'}}})
        self.assertEqual(self.load({'backend':'a','backends':{'a':{'base_url':'http://127.0.0.1:8082/v1','model':'m'}}}).backends['a'].model,'m')
    def test_invalid_config_fails_closed(self):
        for data in [{'timeout_seconds':999},{'timeout_seconds':float('nan')},{'backend':'missing'},{'fallbacks':['a']},{'backends':[]},{'max_tokens':False},{'unknown':True}]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):self.load(data)
    def test_public_listener_is_refused(self):
        with self.assertRaises(ValueError):app.LocalServer(('0.0.0.0',0),app.Config(None,{}))

class RequestTests(unittest.TestCase):
    def test_health_and_readiness_distinguish_unconfigured_loading_and_ready(self):
        with gateway(app.Config(None,{})) as g:
            self.assertEqual(request(g,'/health'),(200,{'ok':True,'configured':False}))
            self.assertEqual(request(g,'/ready')[1]['state'],'unconfigured')
            self.assertEqual(request(g,'/v1/chat/completions',PROMPT)[0],503)
        with engine(mode='loading') as e:
            with gateway(app.Config('a',{'a':profile('a',e)})) as g:
                self.assertEqual(request(g,'/ready')[0],503)
                e.mode='ok';self.assertEqual(request(g,'/ready')[0],200)
                self.assertEqual(request(g,'/ready')[1]['state'],'ready')
    def test_per_backend_models_and_shared_fallback_configuration(self):
        with engine('npu-model','fail') as first,engine('gpu-model') as second:
            config=app.Config('npu',{'npu':profile('npu',first),'gpu':profile('gpu',second)},('gpu',),2,64)
            with gateway(config) as g:
                self.assertEqual(request(g,'/v1/chat/completions',{**PROMPT,'model':'client-override','max_tokens':10000})[0],200)
            self.assertEqual(first.calls[0]['model'],'npu-model');self.assertEqual(second.calls[0]['model'],'gpu-model')
            self.assertEqual(second.calls[0]['max_tokens'],64)
    def test_invalid_accepted_reply_does_not_fallback(self):
        with engine('npu-model','invalid') as first,engine('cpu-model') as second:
            config=app.Config('npu',{'npu':profile('npu',first),'cpu':profile('cpu',second)},('cpu',),2)
            with gateway(config) as g:self.assertEqual(request(g,'/v1/chat/completions',PROMPT)[0],502)
            self.assertEqual(second.calls,[])
    def test_stream_is_forwarded_before_generation_finishes(self):
        with engine(mode='stream') as e:
            with gateway(app.Config('a',{'a':profile('a',e)},(),2)) as g:
                c=http.client.HTTPConnection('127.0.0.1',g.server_port,timeout=3)
                c.request('POST','/v1/chat/completions',body=json.dumps({**PROMPT,'stream':True}),headers={'Content-Type':'application/json'})
                r=c.getresponse();self.assertEqual(r.status,200)
                first=r.read1(4096);self.assertIn(b'hello',first);self.assertNotIn(b'[DONE]',first)
                e.release.set();self.assertIn(b'[DONE]',r.read());c.close()
    def test_wrong_stream_content_type_returns_a_valid_http_error(self):
        with engine() as e,gateway(app.Config('a',{'a':profile('a',e)})) as g:
            self.assertEqual(request(g,'/v1/chat/completions',{**PROMPT,'stream':True})[0],502)
    def test_truncated_stream_reports_error_without_retrying(self):
        with engine('npu-model','truncated-stream') as first,engine('cpu-model') as second:
            config=app.Config('npu',{'npu':profile('npu',first),'cpu':profile('cpu',second)},('cpu',),2)
            with gateway(config) as g:
                c=http.client.HTTPConnection('127.0.0.1',g.server_port,timeout=3)
                c.request('POST','/v1/chat/completions',body=json.dumps({**PROMPT,'stream':True}),headers={'Content-Type':'application/json'})
                r=c.getresponse();self.assertEqual(r.status,200);body=r.read();c.close()
                self.assertIn(b'hello',body);self.assertIn(b'event: error',body)
            self.assertEqual(second.calls,[])
    def test_slow_drip_cannot_extend_total_deadline(self):
        with engine(mode='drip') as e:
            with gateway(app.Config('a',{'a':profile('a',e)},(),.3)) as g:
                start=time.monotonic();status,_=request(g,'/v1/chat/completions',PROMPT)
                self.assertEqual(status,504);self.assertLess(time.monotonic()-start,1.2)
    def test_only_one_inference_is_accepted_at_a_time(self):
        with engine(mode='hold') as e:
            with gateway(app.Config('a',{'a':profile('a',e)},(),2)) as g:
                result=[];t=threading.Thread(target=lambda:result.append(request(g,'/v1/chat/completions',PROMPT)))
                t.start();self.assertTrue(e.entered.wait(1))
                self.assertEqual(request(g,'/v1/chat/completions',PROMPT)[0],429)
                e.release.set();t.join();self.assertEqual(result[0][0],200)
    def test_prompt_and_answer_are_not_logged(self):
        logs=io.StringIO()
        with engine() as e,gateway(app.Config('a',{'a':profile('a',e)})) as g,redirect_stdout(logs):
            self.assertEqual(request(g,'/v1/chat/completions',PROMPT)[0],200)
            self.assertTrue(g.inference.acquire(timeout=1));g.inference.release()
        self.assertNotIn('private spoken phrase',logs.getvalue());self.assertNotIn('answer',logs.getvalue())
        record=json.loads(logs.getvalue());self.assertIn('total_ms',record);self.assertIn('first_byte_ms',record);self.assertIn('probe_ms',record['attempts'][0]);self.assertIn('headers_ms',record['attempts'][0])
    def test_malformed_request_is_rejected(self):
        with gateway(app.Config(None,{})) as g:
            for body in [{'messages':[]},{'messages':[{'role':'tool','content':'x'}]},{'messages':[{'role':'user','content':7}]},{**PROMPT,'stream':'yes'}]:
                self.assertEqual(request(g,'/v1/chat/completions',body)[0],400)

class DiagnosticsTests(unittest.TestCase):
    def test_reads_metrics_without_altering_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sysroot=root/'sys';proc=root/'proc';proc.mkdir()
            files={'devices/system/cpu/cpufreq/policy4/scaling_governor':'schedutil',
                   'devices/system/cpu/cpufreq/policy4/scaling_cur_freq':'1800000',
                   'class/thermal/thermal_zone0/type':'soc','class/thermal/thermal_zone0/temp':'41000'}
            for name,text in files.items():p=sysroot/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            (proc/'meminfo').write_text('MemAvailable: 4000 kB\nSwapTotal: 0 kB\n')
            result=app.diagnostics(sysroot,proc)
            self.assertEqual(result['thermal'][0]['temperature_millicelsius'],'41000')
            self.assertEqual(result['memory']['MemAvailable'],'4000 kB')
            for name,text in files.items():self.assertEqual((sysroot/name).read_text(),text)

class BodyTimingTests(unittest.TestCase):
    def test_first_byte_callback_runs_before_remaining_body_reads(self):
        called=[]
        class Response:
            def __init__(self):self.index=0
            def read1(self,n):
                self.index+=1
                if self.index==1:return b'{' 
                if self.index==2:
                    if not called:raise AssertionError('First byte was not recorded before reading the remaining body')
                    return b'}'
                return b''
        self.assertEqual(app.read_limited(Response(),app.Deadline(2),lambda:called.append(True)),b'{}')
        self.assertEqual(called,[True])

class CLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery,importlib.util
        loader=importlib.machinery.SourceFileLoader('chatbox_cli',str(ROOT/'overlay/usr/local/sbin/chatbox-api'))
        spec=importlib.util.spec_from_loader(loader.name,loader);cls.cli=importlib.util.module_from_spec(spec);loader.exec_module(cls.cli)
    def test_cli_health_and_unconfigured_readiness(self):
        from contextlib import redirect_stderr
        with gateway(app.Config(None,{})) as g:
            out=io.StringIO();err=io.StringIO()
            with redirect_stdout(out):self.assertEqual(self.cli.main(['health'],port=g.server_port),0)
            self.assertTrue(json.loads(out.getvalue())['ok'])
            with redirect_stderr(err):self.assertEqual(self.cli.main(['ready'],port=g.server_port),1)
            self.assertEqual(json.loads(err.getvalue())['state'],'unconfigured')
    def test_cli_text_and_streaming(self):
        with engine() as e,gateway(app.Config('a',{'a':profile('a',e)})) as g:
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(self.cli.main(['chat','Hello'],port=g.server_port),0)
                self.assertTrue(g.inference.acquire(timeout=1));g.inference.release()
            self.assertIn('answer',out.getvalue())
            e.mode='stream';e.release.set();out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(self.cli.main(['chat','Hello','--stream'],port=g.server_port),0)
                self.assertTrue(g.inference.acquire(timeout=1));g.inference.release()
            self.assertIn('hello',out.getvalue())
