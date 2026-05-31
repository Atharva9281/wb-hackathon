import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import toast from "react-hot-toast";
import { Copy, FileText, FileType2, Check } from "lucide-react";
import { useQueryStore } from "@/store/useQueryStore";
import { exportPdf, exportDocx } from "@/lib/exportAnswer";

export function AnswerPanel() {
  const answer = useQueryStore((s) => s.answer);
  const question = useQueryStore((s) => s.question);
  const status = useQueryStore((s) => s.status);
  const [copied, setCopied] = useState(false);
  const disabled = !answer || status === "running";

  const handleCopy = async () => {
    if (!answer) return;
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      toast.error("Copy failed");
    }
  };

  const handlePdf = () => {
    try {
      exportPdf(question, answer);
    } catch (e: any) {
      toast.error(e?.message || "PDF export failed");
    }
  };

  const handleDocx = async () => {
    try {
      await exportDocx(question, answer);
    } catch (e: any) {
      toast.error(e?.message || "DOCX export failed");
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Answer
        </div>
        <div className="flex items-center gap-1">
          <IconBtn label="Copy" onClick={handleCopy} disabled={disabled}>
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </IconBtn>
          <IconBtn label="Download PDF" onClick={handlePdf} disabled={disabled}>
            <FileText className="h-3.5 w-3.5" />
          </IconBtn>
          <IconBtn label="Download DOCX" onClick={handleDocx} disabled={disabled}>
            <FileType2 className="h-3.5 w-3.5" />
          </IconBtn>
        </div>
      </div>

      <div className="mt-3 min-h-[180px]">
        {!answer ? (
          <div className="card-soft flex h-44 items-center justify-center text-sm text-muted-foreground">
            Run a query to see results
          </div>
        ) : (
          <div className="card-soft p-4 md-answer text-[13.5px] leading-relaxed text-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function IconBtn({
  children,
  onClick,
  disabled,
  label,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="rounded-md p-1.5 text-muted-foreground transition hover:bg-panel hover:text-charcoal disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
    >
      {children}
    </button>
  );
}
