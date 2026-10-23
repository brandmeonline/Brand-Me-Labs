const urls=[process.env.BRANDME_GATEWAY_HEALTH_URL,process.env.BRANDME_CONSUMER_URL,process.env.BRANDME_CONSOLE_URL].filter(Boolean)
for(const url of urls){
  let ready=false
  for(let attempt=0;attempt<60;attempt++){
    try{if((await fetch(url,{signal:AbortSignal.timeout(1000)})).ok){ready=true;break}}catch{}
    await new Promise(resolve=>setTimeout(resolve,1000))
  }
  if(!ready)throw new Error(`Application did not become ready: ${url}`)
}
