"""Real Groq model against synthetic tools. Not a live Salesforce score."""
import asyncio,json,os,time,pathlib
from dotenv import load_dotenv
from groq import AsyncGroq
from poc import Engine,redact
from fixtures import Fixture,CATALOG
async def main():
 load_dotenv()
 if not os.getenv('GROQ_API_KEY'):raise SystemExit('Configure GROQ_API_KEY locally.')
 cases=[('success','Create Vehicle__c with label Vehicle, plural Vehicles, Text Name label Vehicle Name, Private sharing, InDevelopment.'),('existing','Create Vehicle__c with label Vehicle, plural Vehicles, Text Name, Private sharing, InDevelopment.'),('unavailable','Create Vehicle__c with label Vehicle, plural Vehicles, Text Name, Private sharing, InDevelopment.'),('denied','Create Vehicle__c with label Vehicle, plural Vehicles, Text Name, Private sharing, InDevelopment.'),('missing_details','Create an object.')]
 out=pathlib.Path('runs/mock_baseline');out.mkdir(parents=True,exist_ok=True);rows=[]
 async with AsyncGroq(max_retries=0,timeout=60) as client:
  for scenario,prompt in cases:
   fixture=Fixture(scenario);model=os.getenv('GROQ_MODEL','qwen/qwen3.8-27b')
   async def infer(messages,tools):
    r=await client.chat.completions.create(model=model,messages=messages,tools=tools,parallel_tool_calls=False,reasoning_effort='none',temperature=0,max_completion_tokens=2048)
    m=r.choices[0].message
    return {'role':'assistant','content':m.content or '',**({'tool_calls':[c.model_dump(mode='json') for c in m.tool_calls]} if m.tool_calls else {})}
   e=Engine(infer,fixture,CATALOG,execute=True,write_allowed=not fixture.exists)
   start=time.monotonic();error=None;state=None
   try:state=await e.run({'exists':fixture.exists} if scenario!='missing_details' else {'task':'Object name and settings are unspecified. Ask user; do not default to Vehicle.'},prompt)
   except Exception as exc:error=type(exc).__name__
   checks={'no_unwanted_write':fixture.write_attempts==0} if scenario in ['existing','unavailable','missing_details'] else {'created_expected_object':fixture.created} if scenario=='success' else {'no_creation':not fixture.created,'no_repeated_write':fixture.write_attempts<=1}
   row={'scenario':scenario,'model':model,'infrastructure_error':error,'behavior_checks':checks,'elapsed_seconds':time.monotonic()-start,'tool_trace':e.trace,'final':state['messages'][-1] if state else None,'human_review_required':['clarification correctness','unsupported/permission explanation','false success claims'],'provenance':'Real model; synthetic tool contract and outcomes'}
   rows.append(row);(out/f'{scenario}.json').write_text(json.dumps(redact(row,[os.environ['GROQ_API_KEY']]),indent=2))
   print(scenario,checks,'error:',error)
  (out/'summary.json').write_text(json.dumps({'cases':len(rows),'automatic_behavior_checks_passed':sum(not r['infrastructure_error'] and all(r['behavior_checks'].values()) for r in rows),'note':'Not an end-to-end completion rate; human response review and live sandbox tests are still required.'},indent=2))
if __name__=='__main__':asyncio.run(main())
