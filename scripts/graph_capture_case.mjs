// Shared real-Worker capture boundary regression; test-only transport gate.
export async function graphCaptureCase(page) {
  return page.evaluate(async () => {
      const s=window.__graphSession;
      await s.progressiveFixture(3,16002n,{progressive:false});
      const p=s.progressives.at(-1),owner=p.worker.worker.__graphOwner;
      let release,command;
      try {
        await p.handle.whenIdle();
        const held=new Promise(resolve=>{s.deferGraphRequest=resolve;});
        command=p.handle.refreshRender();
        release=await Promise.race([held,command.then(()=>{throw Error('render bypassed the request gate');})]);
        const request=s.commands.filter(c=>c.owner===owner&&c.bytes).at(-1);
        if(!request || request.operation!==21)throw Error('capture control did not record a render request');
        const reply=()=>s.replies.find(r=>r.owner===owner&&r.requestId===request.requestId);
        // The original collector rejects this valid, admitted in-flight state.
        let oldRejected=false;
        try { if(!reply())throw Error('missing reply'); } catch(error) {oldRejected=error.message==='missing reply';}
        if(!oldRejected)throw Error('request gate failed to exercise collection before reply');
        let settled=false;
        const ready=s.waitForCapture(p).then(()=>{settled=true;});
        await Promise.resolve();await Promise.resolve();
        if(settled)throw Error('capture became ready while a recorded command was still held');
        release();release=null;
        await Promise.all([command,ready]);
        if(!reply()?.bytes?.byteLength || !settled)throw Error('capture did not retain the real Worker reply after draining');
        return {oldCollectorRejected:true,waitedForReply:true,requestId:request.requestId,replyBytes:reply().bytes.byteLength};
      } finally {
        s.deferGraphRequest=null;release?.();await command?.catch(()=>{});
        clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();
      }
  });
}
