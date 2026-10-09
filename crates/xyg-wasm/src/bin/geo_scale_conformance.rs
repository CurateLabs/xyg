//! Persistent bounded native oracle for the actual retained-source processor.
//! One hexadecimal XYGQ request per line; replies are hex or ERROR:<stable-code>.
use std::io::{self, BufRead, Read, Write};
use xyg_engine::geo_scale_protocol::{HEADER, MAX_DATA, execute, read_data};
use xyg_engine::geo_source::{MAX_PROCESSOR_BYTES, SourceError};
fn nibble(v: u8) -> Option<u8> {
    match v {
        b'0'..=b'9' => Some(v - b'0'),
        b'a'..=b'f' => Some(v - b'a' + 10),
        b'A'..=b'F' => Some(v - b'A' + 10),
        _ => None,
    }
}
fn run(line: &[u8], budget: usize) -> Result<Vec<u8>, SourceError> {
    let line = line.strip_suffix(b"\n").unwrap_or(line);
    let line = line.strip_suffix(b"\r").unwrap_or(line);
    if line.len() < HEADER * 2 || !line.len().is_multiple_of(2) || line.len() > MAX_DATA * 2 {
        return Err(SourceError::InvalidFrame);
    }
    let mut request = Vec::with_capacity(line.len() / 2);
    for p in line.chunks_exact(2) {
        request.push(
            nibble(p[0])
                .zip(nibble(p[1]))
                .map(|(a, b)| a * 16 + b)
                .ok_or(SourceError::InvalidFrame)?,
        );
    }
    if request.len() > budget {
        return Err(SourceError::ResourceLimit);
    }
    let command = u32::from_le_bytes(request[8..12].try_into().unwrap());
    if !matches!(command, 20 | 21 | 23 | 25 | 30 | 40) {
        execute(&request).map(|reply| reply.to_vec())
    } else {
        read_data(&request, budget)
    }
}
fn main() {
    let budget = std::env::args()
        .nth(1)
        .and_then(|v| v.parse().ok())
        .unwrap_or(MAX_PROCESSOR_BYTES);
    if !(HEADER..=MAX_PROCESSOR_BYTES).contains(&budget) {
        eprintln!("{}", SourceError::ResourceLimit.code());
        std::process::exit(3);
    }
    let input = io::stdin();
    let mut input = input.lock();
    let output = io::stdout();
    let mut output = output.lock();
    loop {
        let max_line = budget.min(MAX_DATA) * 2 + 1;
        let mut line = Vec::new();
        let read = input
            .by_ref()
            .take(max_line as u64 + 1)
            .read_until(b'\n', &mut line);
        match read {
            Ok(0) => break,
            Err(_) => std::process::exit(2),
            _ => {}
        }
        if line.len() > max_line {
            let _ = writeln!(output, "ERROR:{}", SourceError::ResourceLimit.code());
            break; // An oversize line is terminal; never interpret its tail as a request.
        }
        match run(&line, budget) {
            Ok(reply) => {
                const HEX: &[u8; 16] = b"0123456789abcdef";
                for byte in reply {
                    if output
                        .write_all(&[HEX[(byte >> 4) as usize], HEX[(byte & 15) as usize]])
                        .is_err()
                    {
                        std::process::exit(2);
                    }
                }
                if writeln!(output).is_err() {
                    std::process::exit(2);
                }
            }
            Err(error) => {
                if writeln!(output, "ERROR:{}", error.code()).is_err() {
                    std::process::exit(2);
                }
            }
        }
        if output.flush().is_err() {
            std::process::exit(2);
        }
    }
}
