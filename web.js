const byId = id => document.getElementById(id);
const statusLine = byId('status');
let running = false;
let urls = [];

function clearResults() {
  for (const url of urls) URL.revokeObjectURL(url);
  urls = [];
  byId('links').replaceChildren();
  byId('notes').replaceChildren();
  byId('results').hidden = true;
}

function addDownload(name, bytes) {
  const link = document.createElement('a');
  const type = name.endsWith('.zip') ? 'application/zip' : 'application/json';
  link.href = URL.createObjectURL(new Blob([bytes], {type}));
  urls.push(link.href);
  link.download = name;
  link.textContent = name;
  byId('links').append(link);
}

function showOutput(output) {
  for (const item of output.files) addDownload(item.name, item.bytes);
  const notes = [...output.report.manual_review, ...output.report.omitted_files.map(f => 'Archivo omitido: ' + f)];
  for (const note of notes.length ? notes : ['El conversor no detectó elementos pendientes.']) {
    const li = document.createElement('li');
    li.textContent = note;
    byId('notes').append(li);
  }
  byId('results').hidden = false;
  statusLine.textContent = 'Conversión terminada · ' + output.report.converted.length + ' skills. Revisa los archivos antes de instalarlos.';
}

async function start(example) {
  if (running) return;
  running = true;
  clearResults();
  for (const id of ['source','language','convert','example']) byId(id).disabled = true;
  let worker;
  try {
    let file = byId('source').files[0];
    if (example) {
      statusLine.textContent = 'Abriendo el ejemplo de un acta…';
      const response = await fetch('./examples/acta-de-ejemplo-claude.zip');
      if (!response.ok) throw Error('No se pudo cargar el ejemplo.');
      file = new File([await response.blob()], 'acta-de-ejemplo-claude.zip');
    }
    if (!file || !(/\.(zip|skill)$/i.test(file.name) || file.name === 'SKILL.md'))
      throw Error('Elige un ZIP, un archivo .skill o un SKILL.md.');
    if (file.size > 64 * 1024 * 1024) throw Error('El archivo supera los 64 MiB.');
    statusLine.textContent = 'Preparando el conversor en tu navegador. La primera carga puede tardar…';
    worker = new Worker('./web-worker.js');
    const buffer = await file.arrayBuffer();
    const result = await new Promise((resolve, reject) => {
      worker.onerror = () => reject(Error('No se pudo iniciar el conversor. Comprueba la conexión y vuelve a intentarlo.'));
      worker.onmessage = ({data}) => {
        if (data.status) statusLine.textContent = data.status;
        else if (data.error) reject(Error(data.error));
        else resolve(data);
      };
      worker.postMessage({name:file.name, buffer, language:byId('language').value}, [buffer]);
    });
    showOutput(result);
  } catch (error) {
    statusLine.textContent = 'Conversión interrumpida. ' + error.message;
  } finally {
    worker?.terminate();
    running = false;
    for (const id of ['source','language','convert','example']) byId(id).disabled = false;
  }
}

byId('converter').addEventListener('submit', e => { e.preventDefault(); start(false); });
byId('example').addEventListener('click', () => start(true));
byId('source').addEventListener('change', () => {clearResults(); statusLine.textContent = '';});
