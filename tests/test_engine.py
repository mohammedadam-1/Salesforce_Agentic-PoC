import asyncio,json
from poc import Engine,redact
from fixtures import Fixture,CATALOG,EXPECTED

def call(n,a):return {'role':'assistant','content':'','tool_calls':[{'id':'c'+n,'type':'function','function':{'name':n,'arguments':json.dumps(a)}}]}
def model_for(seq):
 async def model(messages,tools):return seq.pop(0) if seq else {'role':'assistant','content':'Done'}
 return model

def sequence():return [call('discover',{'query':'create custom object'}),call('describe',{'operation':'create_object'}),call('dispatch',{'operation':'create_object','inputs':{'metadata':EXPECTED}})]
def run(seq,fixture,**kw):
 e=Engine(model_for(seq),fixture,CATALOG,**kw);asyncio.run(e.run({'exists':fixture.exists},'Create Vehicle__c'));return e

def test_native_call_loop():
 f=Fixture('success');e=run(sequence(),f,execute=True);assert f.created and e.writes==1

def test_dry_run_blocks_write():
 f=Fixture('success');e=run(sequence(),f);assert not f.created and e.writes==0

def test_duplicate_guard():
 f=Fixture('existing');e=run(sequence(),f,execute=True,write_allowed=False);assert f.write_attempts==0

def test_schema_rejection():
 f=Fixture('success');e=run([call('discover',{'invented':'x'})],f);assert not e.discovered and any(t['kind']=='rejected_or_failed_call' for t in e.trace)

def test_describe_order():
 f=Fixture('success');e=run([call('describe',{'operation':'create_object'})],f);assert not e.described

def test_permission_failure_stops_loop():
 f=Fixture('denied');e=run(sequence()+[call('dispatch',{'operation':'create_object','inputs':{'metadata':EXPECTED}})],f,execute=True);assert e.blocked and f.write_attempts==1

def test_timeout_does_not_retry():
 class Timeout(Fixture):
  async def __call__(self,n,a):
   if n=='dispatch':self.write_attempts+=1;raise TimeoutError()
   return await super().__call__(n,a)
 f=Timeout('success');e=run(sequence()*2,f,execute=True);assert e.blocked and f.write_attempts==1

def test_redaction():assert redact({'Authorization':'abc','nested':['mysecret']},['mysecret'])=={'Authorization':'[REDACTED]','nested':['[REDACTED]']}
