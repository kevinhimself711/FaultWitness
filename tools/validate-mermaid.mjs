import { execFile } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const root = process.cwd();
const ignored = new Set([".git", ".venv", "node_modules"]);

async function markdownFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (ignored.has(entry.name)) continue;
    const resolved = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await markdownFiles(resolved)));
    else if (entry.isFile() && entry.name.endsWith(".md")) files.push(resolved);
  }
  return files;
}

function diagrams(text) {
  return [...text.matchAll(/```mermaid\r?\n([\s\S]*?)```/g)].map((match) => match[1].trim());
}

function chromeCandidates() {
  const programFiles = process.env.ProgramFiles || "C:\\Program Files";
  const programFilesX86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  return process.platform === "win32"
    ? [
        path.join(programFiles, "Google", "Chrome", "Application", "chrome.exe"),
        path.join(programFilesX86, "Microsoft", "Edge", "Application", "msedge.exe"),
      ]
    : ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"];
}

async function findChrome() {
  for (const candidate of chromeCandidates()) {
    try {
      if ((await stat(candidate)).isFile()) return candidate;
    } catch {
      // Try the next fixed system-browser location.
    }
  }
  throw new Error("No approved system Chrome/Chromium executable found for Mermaid rendering");
}

const inputs = [];
for (const file of await markdownFiles(root)) {
  const text = await readFile(file, "utf8");
  diagrams(text).forEach((source, index) => inputs.push({ file, index, source }));
}
if (inputs.length === 0) throw new Error("No Mermaid diagrams found");

const temporary = await mkdtemp(path.join(tmpdir(), "faultwitness-mermaid-"));
try {
  const config = path.join(temporary, "puppeteer.json");
  await writeFile(
    config,
    JSON.stringify({ executablePath: await findChrome(), args: ["--no-sandbox"] }),
    "utf8",
  );
  for (const [index, input] of inputs.entries()) {
    const source = path.join(temporary, `${index}.mmd`);
    const output = path.join(temporary, `${index}.svg`);
    await writeFile(source, `${input.source}\n`, "utf8");
    await execFileAsync(
      "pnpm",
      ["exec", "mmdc", "--quiet", "-p", config, "-i", source, "-o", output],
      { cwd: root, shell: process.platform === "win32" },
    );
    if (!(await readFile(output, "utf8")).includes("<svg")) {
      throw new Error(
        `${path.relative(root, input.file)} diagram ${input.index + 1} did not render SVG`,
      );
    }
  }
} finally {
  await rm(temporary, { recursive: true, force: true });
}

console.log(`PASS mermaid-render: ${inputs.length} diagrams`);
