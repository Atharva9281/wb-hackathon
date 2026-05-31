import jsPDF from "jspdf";
import { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } from "docx";
import { saveAs } from "file-saver";

interface Block {
  type: "h1" | "h2" | "h3" | "p" | "li" | "code" | "blank";
  text: string;
}

function parseMarkdown(md: string): Block[] {
  const out: Block[] = [];
  const lines = md.split(/\r?\n/);
  let inCode = false;
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (line.startsWith("```")) {
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      out.push({ type: "code", text: raw });
      continue;
    }
    if (!line.trim()) {
      out.push({ type: "blank", text: "" });
      continue;
    }
    if (line.startsWith("### ")) out.push({ type: "h3", text: line.slice(4) });
    else if (line.startsWith("## ")) out.push({ type: "h2", text: line.slice(3) });
    else if (line.startsWith("# ")) out.push({ type: "h1", text: line.slice(2) });
    else if (/^\s*[-*+]\s+/.test(line))
      out.push({ type: "li", text: line.replace(/^\s*[-*+]\s+/, "") });
    else if (/^\s*\d+\.\s+/.test(line))
      out.push({ type: "li", text: line.replace(/^\s*\d+\.\s+/, "") });
    else out.push({ type: "p", text: line });
  }
  // strip inline markdown emphasis/code markers
  return out.map((b) => ({
    ...b,
    text: b.type === "code"
      ? b.text
      : b.text
          .replace(/\*\*(.+?)\*\*/g, "$1")
          .replace(/\*(.+?)\*/g, "$1")
          .replace(/`([^`]+)`/g, "$1"),
  }));
}

function fileSafe(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "answer";
}

export function exportPdf(question: string, answer: string) {
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const margin = 56;
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const maxW = pageW - margin * 2;
  let y = margin;

  const newPageIfNeeded = (h: number) => {
    if (y + h > pageH - margin) {
      doc.addPage();
      y = margin;
    }
  };

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.setTextColor(17, 24, 39);
  const titleLines = doc.splitTextToSize(question || "QueryMind Answer", maxW);
  titleLines.forEach((l: string) => {
    newPageIfNeeded(22);
    doc.text(l, margin, y);
    y += 22;
  });
  y += 8;

  // Subtle rule
  doc.setDrawColor(229, 231, 235);
  doc.line(margin, y, pageW - margin, y);
  y += 18;

  const blocks = parseMarkdown(answer || "");
  for (const b of blocks) {
    if (b.type === "blank") {
      y += 8;
      continue;
    }
    let size = 11;
    let style: "normal" | "bold" = "normal";
    let font: "helvetica" | "courier" = "helvetica";
    let prefix = "";
    let lh = 16;
    let color: [number, number, number] = [55, 65, 81];

    if (b.type === "h1") { size = 16; style = "bold"; lh = 22; color = [17, 24, 39]; }
    else if (b.type === "h2") { size = 14; style = "bold"; lh = 20; color = [17, 24, 39]; }
    else if (b.type === "h3") { size = 12; style = "bold"; lh = 18; color = [17, 24, 39]; }
    else if (b.type === "li") { prefix = "•  "; }
    else if (b.type === "code") { font = "courier"; size = 10; lh = 14; color = [37, 99, 235]; }

    doc.setFont(font, style);
    doc.setFontSize(size);
    doc.setTextColor(...color);
    const indent = b.type === "li" ? 14 : 0;
    const wrapW = maxW - indent;
    const text = prefix + b.text;
    const lines = doc.splitTextToSize(text, wrapW);
    for (let i = 0; i < lines.length; i++) {
      newPageIfNeeded(lh);
      doc.text(lines[i], margin + indent, y);
      y += lh;
    }
    if (b.type === "h1" || b.type === "h2" || b.type === "h3") y += 4;
  }

  doc.save(`querymind-${fileSafe(question)}.pdf`);
}

export async function exportDocx(question: string, answer: string) {
  const blocks = parseMarkdown(answer || "");
  const children: Paragraph[] = [
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      alignment: AlignmentType.LEFT,
      children: [new TextRun({ text: question || "QueryMind Answer", bold: true })],
    }),
    new Paragraph({ children: [new TextRun({ text: "" })] }),
  ];

  for (const b of blocks) {
    if (b.type === "blank") {
      children.push(new Paragraph({ children: [new TextRun("")] }));
      continue;
    }
    if (b.type === "h1") {
      children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: b.text, bold: true })] }));
    } else if (b.type === "h2") {
      children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: b.text, bold: true })] }));
    } else if (b.type === "h3") {
      children.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: b.text, bold: true })] }));
    } else if (b.type === "li") {
      children.push(new Paragraph({ bullet: { level: 0 }, children: [new TextRun(b.text)] }));
    } else if (b.type === "code") {
      children.push(new Paragraph({ children: [new TextRun({ text: b.text, font: "Consolas" })] }));
    } else {
      children.push(new Paragraph({ children: [new TextRun(b.text)] }));
    }
  }

  const doc = new Document({
    styles: {
      default: { document: { run: { font: "Calibri", size: 22 } } },
    },
    sections: [{ children }],
  });
  const blob = await Packer.toBlob(doc);
  saveAs(blob, `querymind-${fileSafe(question)}.docx`);
}
