// Renders comment bodies as GitHub-flavored markdown. Safe by default — react-markdown
// does not render raw HTML, so user-typed comment text cannot inject markup.
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Render *children* (a markdown string) as styled, sanitized HTML. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="md-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
