import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'markdown',
  standalone: true,
  pure: true
})
export class MarkdownPipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    if (!value) return '';

    const normalized = value.replace(/\r\n?/g, '\n');
    const codeBlocks: string[] = [];
    let source = this.escapeHtml(normalized).replace(/```([\w+-]*)\n([\s\S]*?)```/g, (_match, language: string, code: string) => {
      const langClass = language ? ` class="language-${this.escapeAttribute(language)}"` : '';
      const index = codeBlocks.push(`<pre><code${langClass}>${code.replace(/\n$/, '')}</code></pre>`) - 1;
      return `\n@@CODE_BLOCK_${index}@@\n`;
    });

    const lines = source.split('\n');
    const html: string[] = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();

      if (!trimmed) {
        index += 1;
        continue;
      }

      const codeMatch = trimmed.match(/^@@CODE_BLOCK_(\d+)@@$/);
      if (codeMatch) {
        html.push(codeBlocks[Number(codeMatch[1])] || '');
        index += 1;
        continue;
      }

      const heading = line.match(/^\s*(#{1,6})\s+(.+)$/);
      if (heading) {
        const level = heading[1].length;
        html.push(`<h${level}>${this.inline(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }

      if (/^\s*(?:---+|___+|\*\*\*+)\s*$/.test(line)) {
        html.push('<hr>');
        index += 1;
        continue;
      }

      if (this.isTableHeader(lines, index)) {
        const headers = this.tableCells(lines[index]);
        const rows: string[][] = [];
        index += 2;
        while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
          rows.push(this.tableCells(lines[index]));
          index += 1;
        }
        html.push(
          '<div class="markdown-table-wrap"><table><thead><tr>' +
          headers.map((cell) => `<th>${this.inline(cell)}</th>`).join('') +
          '</tr></thead><tbody>' +
          rows.map((row) => '<tr>' + row.map((cell) => `<td>${this.inline(cell)}</td>`).join('') + '</tr>').join('') +
          '</tbody></table></div>'
        );
        continue;
      }

      if (/^\s*>\s?/.test(line)) {
        const quotes: string[] = [];
        while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
          quotes.push(lines[index].replace(/^\s*>\s?/, ''));
          index += 1;
        }
        html.push(`<blockquote>${quotes.map((item) => this.inline(item)).join('<br>')}</blockquote>`);
        continue;
      }

      if (/^\s*[-+*]\s+/.test(line)) {
        const items: string[] = [];
        while (index < lines.length && /^\s*[-+*]\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*[-+*]\s+/, ''));
          index += 1;
        }
        html.push(`<ul>${items.map((item) => `<li>${this.inline(item)}</li>`).join('')}</ul>`);
        continue;
      }

      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items: string[] = [];
        while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*\d+[.)]\s+/, ''));
          index += 1;
        }
        html.push(`<ol>${items.map((item) => `<li>${this.inline(item)}</li>`).join('')}</ol>`);
        continue;
      }

      const paragraph: string[] = [line.trim()];
      index += 1;
      while (
        index < lines.length &&
        lines[index].trim() &&
        !/^\s*(#{1,6})\s+/.test(lines[index]) &&
        !/^\s*>\s?/.test(lines[index]) &&
        !/^\s*[-+*]\s+/.test(lines[index]) &&
        !/^\s*\d+[.)]\s+/.test(lines[index]) &&
        !/^@@CODE_BLOCK_\d+@@$/.test(lines[index].trim()) &&
        !this.isTableHeader(lines, index)
      ) {
        paragraph.push(lines[index].trim());
        index += 1;
      }
      html.push(`<p>${paragraph.map((item) => this.inline(item)).join('<br>')}</p>`);
    }

    return html.join('');
  }

  private inline(text: string): string {
    const inlineCode: string[] = [];
    let output = text.replace(/`([^`]+)`/g, (_match, code: string) => {
      const index = inlineCode.push(`<code>${code}</code>`) - 1;
      return `@@INLINE_CODE_${index}@@`;
    });

    output = output
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
      .replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>')
      .replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    return output.replace(/@@INLINE_CODE_(\d+)@@/g, (_match, rawIndex: string) => inlineCode[Number(rawIndex)] || '');
  }

  private isTableHeader(lines: string[], index: number): boolean {
    if (index + 1 >= lines.length || !lines[index].includes('|')) return false;
    const separator = lines[index + 1].trim();
    return /^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$/.test(separator);
  }

  private tableCells(line: string): string[] {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
  }

  private escapeHtml(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  private escapeAttribute(value: string): string {
    return value.replace(/[^a-zA-Z0-9_+-]/g, '');
  }
}
