# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/09b_processors.ipynb.

# %% auto 0
__all__ = ['is_frontmatter', 'yml2dict', 'populate_language', 'insert_warning', 'cell_lang', 'add_show_docs', 'yaml_str',
           'nb_fmdict', 'filter_fm', 'construct_fm', 'insert_frontmatter', 'add_links', 'strip_ansi',
           'strip_hidden_metadata', 'hide_', 'hide_line', 'filter_stream_', 'clean_magics', 'rm_header_dash',
           'rm_export', 'clean_show_doc', 'exec_show_docs']

# %% ../nbs/09b_processors.ipynb 2
import ast

from .config import *
from .imports import *
from .process import *
from .showdoc import *
from .doclinks import *

from execnb.nbio import *
from execnb.shell import *
from fastcore.imports import *
from fastcore.xtras import *
import sys,yaml

# %% ../nbs/09b_processors.ipynb 7
_re_fm = re.compile(r'^---(.*\S+.*)---', flags=re.DOTALL)

def is_frontmatter(nb):
    "List of raw cells in `nb` that contain frontmatter"
    return _celltyp(nb, 'raw').filter(lambda c: _re_fm.search(c.get('source', '')))

def yml2dict(s:str, rm_fence=True):
    "convert a string that is in a yaml format to a dict"
    if rm_fence: 
        match = _re_fm.search(s.strip())
        if match: s = match.group(1)
    return yaml.safe_load(s)

def _get_frontmatter(nb):
    cell = first(is_frontmatter(nb))
    return cell,(yml2dict(cell.source) if cell else {})

# %% ../nbs/09b_processors.ipynb 8
_langs = 'bash|html|javascript|js|latex|markdown|perl|ruby|sh|svg'
_lang_pattern = re.compile(rf'^\s*%%\s*({_langs})\s*$', flags=re.MULTILINE)

class populate_language(Processor):
    "Set cell language based on NB metadata and magics"
    def begin(self): self.language = nb_lang(self.nb)
    def cell(self, cell):
        if cell.cell_type != 'code': return
        lang = _lang_pattern.findall(cell.source)
        if lang: cell.metadata.language = lang[0]
        else: cell.metadata.language = self.language

# %% ../nbs/09b_processors.ipynb 10
class insert_warning(Processor):
    "Insert Autogenerated Warning Into Notebook after the first cell."
    content = "<!-- WARNING: THIS FILE WAS AUTOGENERATED! DO NOT EDIT! -->"
    def begin(self): self.nb.cells.insert(1, mk_cell(self.content, 'markdown'))

# %% ../nbs/09b_processors.ipynb 14
_def_types = (ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)
def _def_names(cell, shown):
    cellp = cell.parsed_()
    return [showdoc_nm(o) for o in concat(cellp)
            if isinstance(o,_def_types) and o.name not in shown and o.name[0]!='_'] if cellp else []

def _get_nm(tree):
    i = tree.value.args[0]
    if hasattr(i, 'id'): val = i.id
    else: val = try_attrs(i.value, 'id', 'func', 'attr')
    return f'{val}.{i.attr}' if isinstance(i, ast.Attribute) else i.id

# %% ../nbs/09b_processors.ipynb 15
def _show_docs(trees):
    return [t for t in trees if isinstance(t,ast.Expr) and nested_attr(t, 'value.func.id')=='show_doc']

def cell_lang(cell): return nested_attr(cell, 'metadata.language', 'python')
def _want_doc(c):
    return c.source and c.cell_type=='code' and (set(['export', 'exports', 'exec_doc']).intersection(c.directives_))

class add_show_docs(Processor):
    "Add show_doc cells after exported cells, unless they are already documented"
    def begin(self):
        nb = self.nb
        exports = L(cell for cell in nb.cells if _want_doc(cell))
        trees = L(nb.cells).map(NbCell.parsed_).concat()
        shown_docs = {_get_nm(t) for t in _show_docs(trees)}
        for cell in reversed(exports):
            if cell_lang(cell) != 'python':  raise ValueError(f"{cell.metadata.language} can't export:\n{cell.source}")
            for nm in _def_names(cell, shown_docs): nb.cells.insert(cell.idx_+1, mk_cell(f'show_doc({nm})'))
        nb.has_docs_ = shown_docs or exports

# %% ../nbs/09b_processors.ipynb 19
def yaml_str(s:str):
    "Create a valid YAML string from `s`"
    if s[0]=='"' and s[-1]=='"': return s
    res = s.replace('\\', '\\\\').replace('"', r'\"')
    return f'"{res}"'

# %% ../nbs/09b_processors.ipynb 20
_re_title = re.compile(r'^#\s+(.*)[\n\r]+(?:^>\s+(.*))?', flags=re.MULTILINE)

def _celltyp(nb, cell_type): return L(nb.cells).filter(lambda c: c.cell_type == cell_type)
def _istitle(cell): 
    txt = cell.get('source', '')
    return bool(_re_title.search(txt)) if txt else False

# %% ../nbs/09b_processors.ipynb 21
def nb_fmdict(nb, remove=True): 
    "Infer the front matter from a notebook's markdown formatting"
    md_cells = _celltyp(nb, 'markdown').filter(_istitle)
    if not md_cells: return {}
    cell = md_cells[0]
    title_match = _re_title.match(cell.source)
    if title_match:
        title,desc=title_match.groups()
        flags = re.findall('^-\s+(.*)', cell.source, flags=re.MULTILINE)
        flags = [s.split(':', 1) for s in flags if ':' in s] if flags else []
        flags = merge({k:v for k,v in flags if k and v}, 
                      {'title':yaml_str(title)}, {'description':yaml_str(desc)} if desc else {})
        if remove: cell['source'] = None
        return yml2dict('\n'.join([f"{k}: {flags[k]}" for k in flags]))
    else: return {}

# %% ../nbs/09b_processors.ipynb 24
def _replace_fm(d:dict, # dictionary you wish to conditionally change
                k:str,  # key to check 
                val:str,# value to check if d[k] == v
                repl_dict:dict #dictionary that will be used as a replacement 
               ):
    "replace key `k` in dict `d` if d[k] == val with `repl_dict`"
    if str(d.get(k, '')).lower().strip() == str(val.lower()).strip():
        d.pop(k)
        d = merge(d, repl_dict)
    return d

def _fp_alias(d):
    "create aliases for fastpages front matter to match Quarto front matter."
    d = _replace_fm(d, 'search_exclude', 'true', {'search':'false'})
    d = _replace_fm(d, 'hide', 'true', {'draft': 'true'})
    return d

# %% ../nbs/09b_processors.ipynb 26
def _fp_image(d):
    "Correct path of fastpages images"
    prefix = 'images/copied_from_nb/'
    if d.get('image', '').startswith(prefix): d['image'] = d['image'].replace(prefix, '')
    return d

# %% ../nbs/09b_processors.ipynb 28
def filter_fm(fmdict:dict):
    "Filter front matter"
    keys = ['title', 'description', 'author', 'image', 'categories', 'output-file', 'aliases', 'search', 'draft', 'comments']
    if not fmdict: return {}
    return filter_keys(fmdict, in_(keys))

# %% ../nbs/09b_processors.ipynb 29
def construct_fm(fmdict:dict):
    "Construct front matter from a dictionary"
    if not fmdict: return None
    return '---\n'+yaml.dump(fmdict)+'\n---'    

# %% ../nbs/09b_processors.ipynb 31
def insert_frontmatter(nb, fm_dict:dict):
    "Add frontmatter into notebook based on `filter_keys` that exist in `fmdict`."
    fm = construct_fm(fm_dict)
    if fm: nb.cells.insert(0, NbCell(0, dict(cell_type='raw', metadata={}, source=fm, directives_={})))

# %% ../nbs/09b_processors.ipynb 33
_re_defaultexp = re.compile(r'^\s*#\|\s*default_exp\s+(\S+)', flags=re.MULTILINE)

def _default_exp(nb):
    "get the default_exp from a notebook"
    code_src = L(nb.cells).filter(lambda x: x.cell_type == 'code').attrgot('source')
    default_exp = first(code_src.filter().map(_re_defaultexp.search).filter())
    return default_exp.group(1) if default_exp else None

# %% ../nbs/09b_processors.ipynb 35
def add_links(cell):
    "Add links to markdown cells"
    nl = NbdevLookup()
    if cell.cell_type == 'markdown': cell.source = nl.linkify(cell.source)
    for o in cell.get('outputs', []):
        if hasattr(o, 'data') and hasattr(o['data'], 'text/markdown'):
            o.data['text/markdown'] = [nl.link_line(s) for s in o.data['text/markdown']]

# %% ../nbs/09b_processors.ipynb 38
_re_ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(cell):
    "Strip Ansi Characters."
    for outp in cell.get('outputs', []):
        if outp.get('name')=='stdout': outp['text'] = [_re_ansi_escape.sub('', o) for o in outp.text]

# %% ../nbs/09b_processors.ipynb 40
def strip_hidden_metadata(cell):
    '''Strips "hidden" metadata property from code cells so it doesn't interfere with docs rendering'''
    if cell.cell_type == 'code' and 'metadata' in cell: cell.metadata.pop('hidden',None)

# %% ../nbs/09b_processors.ipynb 41
def hide_(cell):
    "Hide cell from output"
    del(cell['source'])

# %% ../nbs/09b_processors.ipynb 43
def _re_hideline(lang=None): return re.compile(fr'{langs[lang]}\|\s*hide_line\s*$', re.MULTILINE)

def hide_line(cell):
    "Hide lines of code in code cells with the directive `hide_line` at the end of a line of code"
    lang = cell_lang(cell)
    if cell.cell_type == 'code' and _re_hideline(lang).search(cell.source):
        cell.source = '\n'.join([c for c in cell.source.splitlines() if not _re_hideline(lang).search(c)])

# %% ../nbs/09b_processors.ipynb 46
def filter_stream_(cell, *words):
    "Remove output lines containing any of `words` in `cell` stream output"
    if not words: return
    for outp in cell.get('outputs', []):
        if outp.output_type == 'stream':
            outp['text'] = [l for l in outp.text if not re.search('|'.join(words), l)]

# %% ../nbs/09b_processors.ipynb 48
_magics_pattern = re.compile(r'^\s*(%%|%).*', re.MULTILINE)

def clean_magics(cell):
    "A preprocessor to remove cell magic commands"
    if cell.cell_type == 'code': cell.source = _magics_pattern.sub('', cell.source).strip()

# %% ../nbs/09b_processors.ipynb 50
_re_hdr_dash = re.compile(r'^#+\s+.*\s+-\s*$', re.MULTILINE)

def rm_header_dash(cell):
    "Remove headings that end with a dash -"
    if cell.source:
        src = cell.source.strip()
        if cell.cell_type == 'markdown' and src.startswith('#') and src.endswith(' -'): del(cell['source'])

# %% ../nbs/09b_processors.ipynb 52
_hide_dirs = {'export','exporti', 'hide','default_exp'}

def rm_export(cell):
    "Remove cells that are exported or hidden"
    if cell.directives_ and (cell.directives_.keys() & _hide_dirs): del(cell['source'])

# %% ../nbs/09b_processors.ipynb 54
_re_showdoc = re.compile(r'^show_doc', re.MULTILINE)
def _is_showdoc(cell): return cell['cell_type'] == 'code' and _re_showdoc.search(cell.source)

def clean_show_doc(cell):
    "Remove ShowDoc input cells"
    if not _is_showdoc(cell): return
    cell.source = '#|output: asis\n#| echo: false\n' + cell.source

# %% ../nbs/09b_processors.ipynb 55
def _ast_contains(trees, types):
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, types): return True

def _do_eval(cell):
    if cell_lang(cell) != 'python': return
    if not cell.source or 'nbdev_export'+'()' in cell.source: return
    trees = cell.parsed_()
    if cell.cell_type != 'code' or not trees: return
    if cell.directives_.get('eval:', [''])[0].lower() == 'false': return

    _show_dirs = {'export','exports','exporti','exec_doc'}
    if cell.directives_.keys() & _show_dirs: return True
    if _ast_contains(trees, (ast.Import, ast.ImportFrom)):
        if _ast_contains(trees, (ast.Expr, ast.Assign)):
            warn(f'Found a cell containing mix of imports and computations. Please use separate cells. See nbdev FAQ.\n---\n{cell.source}\n---\n')
        return True
    if _show_docs(trees): return True

# %% ../nbs/09b_processors.ipynb 56
class exec_show_docs(Processor):
    "Execute cells needed for `show_docs` output, including exported cells and imports"
    def begin(self):
        if nb_lang(self.nb) != 'python': return
        self.k = CaptureShell()
        self.k.run_cell('from nbdev.showdoc import show_doc')

    def __call__(self, cell):
        if not self.nb.has_docs_ or not hasattr(self, 'k'): return
        fm = getattr(self.nb, 'frontmatter_', {})
        if str2bool(fm.get('skip_showdoc', False)): return
        if _do_eval(cell): self.k.cell(cell)
        title = fm.get('title', '')
        if self.k.exc: raise Exception(f"Error{' in notebook: '+title if title else ''} in cell {cell.idx_} :\n{cell.source}") from self.k.exc[1]
