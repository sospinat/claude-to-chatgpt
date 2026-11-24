// Each conversion gets a fresh interpreter and an in-memory filesystem.
const runtimeURL = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
self.onmessage = async ({data}) => {
  try {
    importScripts(runtimeURL + 'pyodide.js');
    const py = await loadPyodide({indexURL: runtimeURL});
    await py.loadPackage('pyyaml');
    const response = await fetch('./plugins/claude-to-chatgpt/skills/translate-claude-package/scripts/translate.py');
    if (!response.ok) throw Error('No se pudo cargar el código del conversor.');
    py.FS.writeFile('/tmp/translate.py', await response.text());
    py.FS.mkdir('/tmp/source');
    const name = data.name === 'SKILL.md' ? data.name : data.name.replace(/[^a-zA-Z0-9._-]/g,'-');
    const path = '/tmp/source/' + name;
    py.FS.writeFile(path, new Uint8Array(data.buffer));
    py.globals.set('source_path', path);
    py.globals.set('language', data.language);
    self.postMessage({status:'Convirtiendo el paquete y preparando las descargas…'});
    const report = JSON.parse(py.runPython(`
import sys, json
from pathlib import Path
sys.path.insert(0, '/tmp')
from translate import read_package, convert, archive_bytes, as_json
entries, label = read_package(Path(source_path))
package, skills, report = convert(entries, label, language)
if Path(source_path).name == 'SKILL.md':
    report['manual_review'].append('Standalone Markdown: attach the complete ZIP if the workflow needs supporting files.')
if sum(map(len, package.values())) > 96 * 1024 * 1024 or len(package) > 8192:
    raise ValueError('El paquete de salida supera el límite de esta versión web.')
out = Path('/tmp/output')
out.mkdir()
(out/'plugin.zip').write_bytes(archive_bytes(package))
(out/'migration.json').write_bytes(as_json(report))
(out/'skills').mkdir()
for name, members in skills.items():
    (out/'skills'/(name+'.zip')).write_bytes(archive_bytes({name+'/'+k:v for k,v in members.items()}))
json.dumps(report)
`));
    const read = (name, path) => ({name, bytes:py.FS.readFile('/tmp/output/'+path)});
    const files = [read(report.package+'-plugin.zip','plugin.zip')];
    for (const item of report.converted) files.push(read(item.skill+'-skill.zip','skills/'+item.skill+'.zip'));
    files.push(read('migration.json','migration.json'));
    self.postMessage({files, report}, files.map(f => f.bytes.buffer));
  } catch (error) {
    const lines = String(error.message || error).trim().split('\n');
    self.postMessage({error:lines.at(-1)});
  }
};
