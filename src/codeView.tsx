import React from "react";

/**
 * Dependency-free syntax tinting for code snippets: comments, strings,
 * numbers and a common keyword set get colored via one tokenizer pass.
 * Not a real parser — good enough for clipboard-sized fragments.
 */

const KEYWORDS =
  /\b(?:fn|let|const|var|function|return|if|else|for|while|loop|match|use|pub|struct|impl|enum|trait|mod|type|async|await|class|extends|new|delete|typeof|instanceof|import|from|export|default|try|catch|finally|throw|switch|case|break|continue|def|lambda|pass|yield|with|as|in|of|not|and|or|None|True|False|null|undefined|true|false|self|this|static|void|int|uint|f32|f64|u8|u16|u32|u64|usize|i8|i16|i32|i64|isize|str|bool|String|Vec|Option|Result|select|insert|update|delete|where|from|group|order|by|join|kubectl)\b/;

interface Tok {
  text: string;
  cls?: string;
}

/** Split text into colored/plain tokens; safe (no HTML injection — React nodes). */
export function tokenizeCode(text: string): Tok[] {
  // single regex alternation: line comment | block comment | string | char | number
  const re =
    /(\/\/[^\n]*|#[^\n]*|--[^\n]*|\/\*[\s\S]*?\*\/)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)|(\b\d[\d_]*(?:\.\d+)?\b)/g;
  const out: Tok[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) pushWords(out, text.slice(last, m.index));
    if (m[1] !== undefined) out.push({ text: m[1], cls: "tok-comment" });
    else if (m[2] !== undefined) out.push({ text: m[2], cls: "tok-str" });
    else out.push({ text: m[3], cls: "tok-num" });
    last = m.index + m[0].length;
  }
  if (last < text.length) pushWords(out, text.slice(last));
  return out;
}

/** Split a plain chunk further into keyword vs rest. */
function pushWords(out: Tok[], chunk: string) {
  const re = new RegExp(KEYWORDS.source, "g");
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(chunk)) !== null) {
    if (m.index > last) out.push({ text: chunk.slice(last, m.index) });
    out.push({ text: m[0], cls: "tok-kw" });
    last = m.index + m[0].length;
  }
  if (last < chunk.length) out.push({ text: chunk.slice(last) });
}

/** Render pre-truncated code text with tinted tokens. */
export function CodeView({ text }: { text: string }) {
  const toks = React.useMemo(() => tokenizeCode(text), [text]);
  return (
    <>
      {toks.map((tk, i) =>
        tk.cls ? (
          <span key={i} className={tk.cls}>
            {tk.text}
          </span>
        ) : (
          <React.Fragment key={i}>{tk.text}</React.Fragment>
        ),
      )}
    </>
  );
}
