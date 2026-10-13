"""Synthetic contracts only; never presented as Salesforce's real schemas."""
import json
SCHEMA={'type':'object','properties':{'operation':{'type':'string'},'inputs':{'type':'object'}},'required':['operation','inputs'],'additionalProperties':False}
CATALOG=[{'name':'discover','description':'Find operations by intent.','inputSchema':{'type':'object','properties':{'query':{'type':'string'}},'required':['query'],'additionalProperties':False}},{'name':'describe','description':'Retrieve operation input schema and dependencies.','inputSchema':{'type':'object','properties':{'operation':{'type':'string'}},'required':['operation'],'additionalProperties':False}},*[{'name':n,'description':'Execute a described operation'+(' in read-only mode.' if n.endswith('readonly') else '.'),'inputSchema':SCHEMA} for n in ['dispatch','dispatch_readonly']]]
EXPECTED={'fullName':'Vehicle__c','label':'Vehicle','pluralLabel':'Vehicles','nameField':{'label':'Vehicle Name','type':'Text'},'sharingModel':'Private','deploymentStatus':'InDevelopment'}
class Fixture:
 def __init__(self,scenario):self.scenario=scenario;self.exists=scenario=='existing';self.created=False;self.write_attempts=0
 async def __call__(self,name,args):
  value={};failed=False
  if name=='discover':value={'candidates':[] if self.scenario=='unavailable' else [{'operation':'inspect_object','description':'Read object metadata'},{'operation':'create_object','description':'Create custom object metadata, not a record'}]}
  elif name=='describe':
   op=args['operation']
   value={'operation':op,'inputSchema':{'type':'object','properties':{'metadata':{'type':'object'}},'required':['metadata']} if op=='create_object' else {'type':'object','properties':{'apiName':{'type':'string'}},'required':['apiName']},'dependencies':['Inspect existence before create'],'allowedSettings':EXPECTED}
  elif name=='dispatch_readonly':
   if args['operation']!='inspect_object':failed=True;value={'error':'UNKNOWN_OPERATION'}
   else:value={'exists':self.exists,'metadata':EXPECTED if self.exists else None}
  elif name=='dispatch':
   self.write_attempts+=1
   if self.scenario=='denied':failed=True;value={'code':'INSUFFICIENT_ACCESS','message':'Metadata creation denied'}
   elif self.exists:failed=True;value={'code':'DUPLICATE_DEVELOPER_NAME'}
   elif args['operation']!='create_object' or args['inputs'].get('metadata')!=EXPECTED:failed=True;value={'code':'INVALID_ARGUMENT','message':'Requested definition did not match the test task'}
   else:self.created=True;self.exists=True;value={'success':True,'fullName':'Vehicle__c'}
  return {'isError':failed,'structuredContent':value,'content':[{'type':'text','text':json.dumps(value)}]}
