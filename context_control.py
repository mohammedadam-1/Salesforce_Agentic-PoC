"""Context and rate controls for the Salesforce headless PoC."""
import asyncio, json, re, time

class ContextBudgetError(RuntimeError):
    pass

def dump(value):
    return json.dumps(value,ensure_ascii=False,default=str)

def estimate_tokens(*values):
    # Rough, conservative enough for rate-limit gating without tokenizer deps.
    return max(1,sum(len(dump(value)) for value in values)//4)

def observation(name,result,max_chars=2400):
    keywords=('custom','object','metadata','create','sobject','field','vehicle','operation','schema','dependency')
    def text(v):
        try:return dump(v).lower()
        except Exception:return str(v).lower()
    def slim(v,depth=0):
        if depth>6:return '[truncated_depth]'
        if isinstance(v,dict):
            kept={}
            for k,val in v.items():
                lk=str(k).lower()
                if lk in {'content','structuredcontent','candidates','operations','tools','inputschema','dependencies','allowedsettings','error','code','message','isexerror','iserror'} or any(word in lk for word in keywords):
                    kept[k]=slim(val,depth+1)
            if not kept:
                for k,val in list(v.items())[:8]:kept[k]=slim(val,depth+1)
            if len(v)>len(kept):kept['_truncated_keys']=len(v)-len(kept)
            return kept
        if isinstance(v,list):
            items=v
            if len(items)>10:
                scored=[item for item in items if any(word in text(item) for word in keywords)]
                items=(scored or items)[:10]
                return [slim(item,depth+1) for item in items]+[{'_truncated_items':len(v)-len(items)}]
            return [slim(item,depth+1) for item in items]
        if isinstance(v,str) and len(v)>800:return v[:800]+'... [truncated]'
        return v
    compact=slim(result)
    rendered=dump(compact)
    if len(rendered)>max_chars:
        return {'tool':name,'isError':result.get('isError') if isinstance(result,dict) else None,'content':[{'type':'text','text':rendered[:max_chars]+'... [truncated for model context]'}]}
    return compact

class GroqBudget:
    def __init__(self,tpm=8000,input_limit=5000,output_limit=1024,max_retries=4):
        self.tpm=tpm;self.input_limit=input_limit;self.output_limit=output_limit;self.max_retries=max_retries;self.stats=[]
    async def complete(self,groq,model,messages,tools):
        estimated=estimate_tokens(messages,tools)
        self.stats.append({'kind':'request_estimate','input_tokens_estimate':estimated,'tool_count':len(tools)})
        if estimated>self.input_limit:
            raise ContextBudgetError('Context budget exceeded before Groq call: estimated input tokens '+str(estimated)+' > '+str(self.input_limit))
        for attempt in range(self.max_retries):
            try:
                started=time.monotonic()
                response=await groq.chat.completions.create(model=model,messages=messages,tools=tools,tool_choice='auto',parallel_tool_calls=False,reasoning_effort='none',temperature=0,max_completion_tokens=self.output_limit)
                self.stats.append({'kind':'completion','elapsed_seconds':time.monotonic()-started})
                return response
            except Exception as exc:
                status=getattr(exc,'status_code',None)
                name=type(exc).__name__
                if status==413:
                    self.stats.append({'kind':'provider_error','status_code':status,'error_class':name})
                    raise ContextBudgetError('Groq rejected request as too large; reduce prompt/tool observations or raise GROQ_INPUT_BUDGET only with a higher-limit model') from exc
                if name!='RateLimitError' and status!=429:raise
                if attempt==self.max_retries-1:raise
                match=re.search(r'try again in ([0-9.]+)s',str(exc),re.I)
                wait=min(float(match.group(1))+1 if match else 10,20)
                event={'kind':'provider_retry','provider':'groq','retry_after_seconds':wait,'error_class':name}
                self.stats.append(event)
                print(dump(event),flush=True)
                await asyncio.sleep(wait)