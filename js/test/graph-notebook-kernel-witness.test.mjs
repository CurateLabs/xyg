import assert from 'node:assert/strict';
import {test} from 'node:test';
import {namedIdleKernel} from '../../scripts/graph_notebook_kernel_witness.mjs';

function fixture({name='Python 3 (ipykernel)', status='idle', text='Idle', editor=true, copyError=false}={}) {
  let reads=0, disposed=0;
  const indicator={getAttribute:()=>++reads===1?status:'busy'};
  globalThis.document={
    body:{innerText:text},
    querySelector:selector=>selector.includes('kernelName')?{getAttribute:()=>name}
      :selector.includes('ExecutionIndicator')?indicator:editor?{}:null,
  };
  return {
    reads:()=>reads, disposed:()=>disposed,
    page:{
      async waitForFunction(predicate, kind, options) {
        assert.equal(options.timeout, 45000);
        const admitted=predicate(kind);
        if(!admitted) throw Error('not admitted');
        return {
          async jsonValue(){if(copyError)throw Error('copy failed');return admitted;},
          async dispose(){disposed++;},
        };
      },
      async evaluate(){throw Error('a second DOM sample can race');},
    },
  };
}

for(const kind of ['jupyterlab','notebook7']) {
  test(`${kind} retains the exact idle state despite the next DOM read being busy`, async()=>{
    const f=fixture();
    assert.deepEqual(await namedIdleKernel(f.page,kind),{name:'Python 3 (ipykernel)',status:'idle'});
    assert.equal(f.reads(),1);assert.equal(f.disposed(),1);
    assert.equal(document.querySelector('.jp-Notebook-ExecutionIndicator').getAttribute('data-status'),'busy');
  });
  for(const options of [{name:'No Kernel'},{name:''},{status:'busy'},{editor:false}]) {
    test(`${kind} refuses ${JSON.stringify(options)}`,async()=>{
      const f=fixture(options);await assert.rejects(namedIdleKernel(f.page,kind),/not admitted/);
      assert.equal(f.disposed(),0);
    });
  }
}
test('Lab still requires its textual Idle evidence',async()=>{
  const f=fixture({text:''});await assert.rejects(namedIdleKernel(f.page,'jupyterlab'),/not admitted/);
});
test('Notebook7 retains its indicator-based admission without Lab text',async()=>{
  const f=fixture({text:''});assert.equal((await namedIdleKernel(f.page,'notebook7')).status,'idle');
});
test('the admitted JSHandle is released even when serialization fails',async()=>{
  const f=fixture({copyError:true});await assert.rejects(namedIdleKernel(f.page,'jupyterlab'),/copy failed/);
  assert.equal(f.disposed(),1);
});
