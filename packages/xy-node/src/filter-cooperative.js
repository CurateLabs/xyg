/** Native scheduling only: every bounded turn and retirement decision is Rust-owned. */
import {filterControlRequest, decodeFilterProgress, filterReplyRetires} from './filter-protocol.js';

function cancelled(message) {
  const error = new Error(message);
  error.code = 'XYG_FILTER_CANCELLED';
  return error;
}

export function nativeFilterLane(executeTurn, release, onTerminal) {
  let active = null, closed = false, closeResult, firstError;
  const retire = (reason) => {
    if (!active) return;
    clearImmediate(active.timer);
    const old = active; active = null;
    old.reject(reason);
  };
  const close = () => {
    if (!closeResult) {
      closed = true;
      retire(firstError ?? cancelled('filter session is closed'));
      closeResult = Promise.resolve();
      try { release(); }
      catch (error) { closeResult = Promise.reject(error); closeResult.catch(() => {}); }
    }
    return closeResult;
  };
  const fail = (entry, error) => {
    firstError ??= error;
    entry.reject(firstError);
    close();
    onTerminal();
  };
  const receive = (entry, response, continuation) => {
    const progress = decodeFilterProgress(response);
    if (progress) {
      if (active && active !== entry) retire(cancelled('filter work was superseded'));
      entry.token = progress.token;
      active = entry;
      entry.timer = setImmediate(() => {
        if (closed || active !== entry) return;
        try { receive(entry, executeTurn(filterControlRequest(2, entry.token)), true); }
        catch (error) { fail(entry, error); }
      });
      return;
    }
    // Even a normal refusal has a Rust watermark. Invalid/stale requests must
    // leave older admitted work and its scheduled turn intact.
    const supersedes = filterReplyRetires(response, active?.token ?? 0n);
    if (active && (continuation || supersedes)) {
      if (active !== entry) retire(cancelled('filter work was superseded'));
      else active = null;
    }
    entry.resolve(response);
  };
  return {
    execute(packet) {
      return new Promise((resolve, reject) => {
        if (closed) { reject(firstError ?? cancelled('filter session is closed')); return; }
        let wrapped;
        try { wrapped = filterControlRequest(1, 0n, packet); }
        catch (error) { reject(error); return; }
        const entry = {resolve, reject, token: 0n, timer: null};
        try { receive(entry, executeTurn(wrapped), false); }
        catch (error) { fail(entry, error); }
      });
    },
    close,
  };
}
