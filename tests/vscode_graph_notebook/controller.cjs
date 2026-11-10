const vscode=require('vscode'),fs=require('node:fs'),path=require('node:path');
exports.run=async()=>{
const output=process.env.XYG_NOTEBOOK_PROBE,record={vscode:vscode.version,appName:vscode.env.appName,appHost:vscode.env.appHost,node:process.versions.node,normalGuiMode:true,events:[]};
const save=()=>{const file=path.join(output,'extension-state.json');fs.writeFileSync(file+'.next',JSON.stringify(record,null,2)+'\n');fs.renameSync(file+'.next',file);};
let collection;
try{
 const document=await vscode.workspace.openNotebookDocument(vscode.Uri.file(path.join(output,'graph.ipynb')));
 await vscode.window.showNotebookDocument(document);
 const extension=vscode.extensions.getExtension('ms-toolsai.jupyter');
 if(!extension)throw Error('actual Jupyter extension missing');
 if(vscode.version!==process.env.XYG_VSCODE_VERSION||extension.packageJSON.version!==process.env.XYG_JUPYTER_EXTENSION_VERSION)throw Error('unqualified VS Code/Jupyter version pair');
 const api=await extension.activate();record.extension={id:extension.id,version:extension.packageJSON.version,api:Object.keys(api)};save();
 const server={id:'xyg-local-kernel',label:'XYG local test kernel',connectionInformation:{baseUrl:vscode.Uri.parse(process.env.XYG_NOTEBOOK_SERVER),token:process.env.XYG_NOTEBOOK_TOKEN}};
 collection=api.createJupyterServerCollection('xyg-notebook-host','XYG local notebook server',{provideJupyterServers:()=>[server],resolveJupyterServer:entry=>entry});
 record.notebook={type:document.notebookType,cellCount:document.cellCount,uri:document.uri.toString()};save();
 const change=vscode.workspace.onDidChangeNotebookDocument(event=>{if(event.notebook===document){record.events.push({at:Date.now(),cells:event.cellChanges.map(x=>({index:x.cell.index,execution:x.executionSummary,outputs:x.outputs?.map(o=>o.items.map(i=>({mime:i.mime,data:Buffer.from(i.data).toString()})))}))});save();}});
 try{
  record.selectionRequested=true;save();
  await vscode.commands.executeCommand('notebook.selectKernel',{});
  record.selectionReturned=true;save();
  const runCell=async(index)=>{
   const args={ranges:[{start:index,end:index+1}],document:document.uri};
   const previousOrder=document.cellAt(index).executionSummary?.executionOrder;
   await vscode.commands.executeCommand('notebook.cell.execute',args);
   const deadline=Date.now()+45000;
   while(document.cellAt(index).executionSummary?.success===undefined||!Number.isSafeInteger(document.cellAt(index).executionSummary?.executionOrder)||document.cellAt(index).executionSummary.executionOrder===previousOrder){if(Date.now()>deadline)throw Error('cell execution did not settle '+index);await new Promise(r=>setTimeout(r,20));}
   const cell=document.cellAt(index);
   await vscode.commands.executeCommand('notebook.cell.collapseCellInput',args);
   if(index===0||index===8)vscode.window.activeNotebookEditor.revealRange(new vscode.NotebookRange(index,index+1),vscode.NotebookEditorRevealType.AtTop);
   const result={index,execution:cell.executionSummary,outputs:cell.outputs.map(o=>o.items.map(i=>({mime:i.mime,data:Buffer.from(i.data).toString()})))};
   record.executed??=[];record.executed.push(result);save();return result;
  };
  await runCell(0);record.executionRequested=true;save();
  let last=0;const stop=Date.now()+210000;
  while(!fs.existsSync(path.join(output,'done'))){
   if(Date.now()>stop)throw Error('probe control deadline');
   const file=path.join(output,'request.json');if(fs.existsSync(file)){
    const request=JSON.parse(fs.readFileSync(file,'utf8'));
    if(request.id>last){last=request.id;let response;if(request.action==='reveal'){vscode.window.activeNotebookEditor.revealRange(new vscode.NotebookRange(request.index,request.index+1),vscode.NotebookEditorRevealType.AtTop);response={revealed:request.index};}else response=await runCell(request.index);const reply=path.join(output,'response-'+last+'.json');fs.writeFileSync(reply+'.next',JSON.stringify(response)+'\n');fs.renameSync(reply+'.next',reply);}
   }
   await new Promise(r=>setTimeout(r,20));
  }
 }finally{change.dispose();}
}catch(error){record.error=error.message;record.stack=error.stack;save();throw error;}
finally{collection?.dispose();}
};
