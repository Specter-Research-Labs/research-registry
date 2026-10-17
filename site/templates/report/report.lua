-- Report apparatus for `spctr doc build`. Runs after citeproc.
-- Numbers sections and appendix entries, builds the contents column, turns
-- footnotes into margin notes and endnotes, expands term notes, collects asset
-- links, refuses external links outside the reference list, and assembles the
-- endmatter.

local function html(content)
  local blocks = content
  if pandoc.utils.type(content) == "Inlines" then
    blocks = { pandoc.Plain(content) }
  end
  return (pandoc.write(pandoc.Pandoc(blocks), "html", { wrap_text = "none" }):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function escape(s)
  return (s:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local function meta_string(meta, key)
  local value = meta[key]
  if value == nil then
    error("report.md: missing metadata field '" .. key .. "'")
  end
  return pandoc.utils.stringify(value)
end

local function inline_note_html(blocks)
  local rendered = html(blocks)
  rendered = rendered:gsub("^%s*<p>", ""):gsub("</p>%s*$", "")
  rendered = rendered:gsub("</p>%s*<p>", "<br><br>")
  return rendered
end

local TERM_FIELDS = { note = true, image = true, caption = true }

-- Builds the inline filter that replaces each `[text]{term=KEY}` span with a
-- pure-CSS hover and focus note from the `terms` front matter. Every glossary
-- entry must be used, because an unused note is usually a renamed key.
local function term_expander(meta)
  local glossary = {}
  local keys = {}
  for key, entry in pairs(meta.terms or {}) do
    if pandoc.utils.type(entry) ~= "table" or entry.note == nil then
      error("report.md: term '" .. key .. "' needs a note")
    end
    for field in pairs(entry) do
      if not TERM_FIELDS[field] then
        error("report.md: term '" .. key .. "' has unknown field '" .. field .. "'")
      end
    end
    if (entry.image == nil) ~= (entry.caption == nil) then
      error("report.md: term '" .. key .. "' needs both image and caption, or neither")
    end
    local image = nil
    if entry.image ~= nil then
      image = pandoc.utils.stringify(entry.image)
      if not image:match("^assets/") then
        error("report.md: term '" .. key .. "' image must be under assets/: " .. image)
      end
      local file = io.open(image, "rb")
      if file == nil then
        error("report.md: term '" .. key .. "' image is missing: " .. image)
      end
      file:close()
    end
    glossary[key] = { note = entry.note, image = image, caption = entry.caption }
    table.insert(keys, key)
  end

  local used = {}
  local filter = { traverse = "topdown" }
  filter.Span = function(span)
    local key = span.attributes.term
    if key == nil then return nil end
    local entry = glossary[key]
    if entry == nil then
      error("report.md: unknown term '" .. key .. "' in: " .. pandoc.utils.stringify(span.content))
    end
    span.content:walk({
      Span = function(inner)
        if inner.attributes.term then
          error("report.md: term '" .. inner.attributes.term .. "' is nested inside term '" .. key .. "'")
        end
      end,
    })
    used[key] = true
    local figure = ""
    if entry.image then
      figure = string.format('<img src="%s" alt=""><span class="rk-term-caption">%s</span>',
        escape(entry.image), inline_note_html(entry.caption))
    end
    local result = pandoc.Inlines({ pandoc.RawInline("html", '<span class="rk-term" tabindex="0">') })
    result:extend(span.content)
    result:insert(pandoc.RawInline("html",
      '<span class="rk-term-note" role="tooltip">' .. figure .. inline_note_html(entry.note) .. "</span></span>"))
    return result
  end

  local function check_all_used()
    local unused = {}
    for _, key in ipairs(keys) do
      if not used[key] then table.insert(unused, key) end
    end
    if #unused > 0 then
      table.sort(unused)
      error("report.md: terms defined but never used: " .. table.concat(unused, ", "))
    end
  end
  return filter, check_all_used
end

local function is_review_link(target, review_hosts)
  local host = target:match("^https?://([^/#?]+)")
  return host ~= nil and review_hosts[host] == true
end

function Pandoc(doc)
  local meta = doc.meta
  for _, key in ipairs({ "title", "subtitle", "kicker", "authors", "document_id", "revision", "year", "url", "abstract" }) do
    meta_string(meta, key)
  end

  local refs_div = nil
  local body = pandoc.Blocks({})
  for _, block in ipairs(doc.blocks) do
    if block.t == "Div" and block.identifier == "refs" then
      refs_div = block
    else
      body:insert(block)
    end
  end

  local review_hosts = {}
  for _, host in ipairs(meta["rk-review-host"] or {}) do
    review_hosts[pandoc.utils.stringify(host)] = true
  end

  for _, block in ipairs(body) do
    if block.t == "Header" then
      block.content:walk({
        Span = function(span)
          if span.attributes.term then
            error("report.md: terms are not allowed in headings: " .. pandoc.utils.stringify(block.content))
          end
        end,
      })
    end
  end
  local expand_terms, check_all_used = term_expander(meta)
  body = body:walk(expand_terms)
  meta.abstract = pandoc.MetaBlocks(pandoc.Blocks(meta.abstract):walk(expand_terms))
  check_all_used()

  local external = {}
  local assets = {}
  local seen_assets = {}
  local function note_asset(target, text)
    if not seen_assets[target] then
      seen_assets[target] = true
      table.insert(assets, { target = target, text = text })
    end
  end
  local function scan_raw(text)
    for href in text:gmatch('href="(https?://[^"]+)"') do
      if not is_review_link(href, review_hosts) then table.insert(external, href) end
    end
    for href, label in text:gmatch('<a[^>]-href="(assets/[^"#]+)"[^>]*>(.-)</a>') do
      note_asset(href, (label:gsub("<[^>]+>", "")))
    end
  end

  local notes = {}
  body = body:walk({
    Link = function(link)
      if link.target:match("^https?://") then
        if not is_review_link(link.target, review_hosts) then table.insert(external, link.target) end
      elseif link.target:match("^assets/") then
        note_asset((link.target:gsub("#.*$", "")), pandoc.utils.stringify(link.content))
      end
    end,
    RawBlock = function(raw)
      if raw.format == "html" then scan_raw(raw.text) end
    end,
    RawInline = function(raw)
      if raw.format == "html" then scan_raw(raw.text) end
    end,
  })
  if #external > 0 then
    error("report.md: external links in the body must be cited as references:\n  " .. table.concat(external, "\n  "))
  end

  body = body:walk({
    Note = function(note)
      table.insert(notes, note.content)
      local n = #notes
      local text = inline_note_html(note.content)
      return pandoc.RawInline("html",
        string.format('<sup class="rk-noteref" id="noteref-%d"><a href="#note-%d">%d</a></sup>' ..
          '<span class="rk-sidenote" aria-hidden="true"><span class="rk-sidenote-num">%d</span> %s</span>',
          n, n, n, n, text))
    end,
  })

  local toc = {}
  local section, sub, appendix_count = 0, 0, 0
  local in_appendix = false
  local current = nil
  body = body:walk({
    Header = function(h)
      if h.classes:includes("appendix") then
        if h.level ~= 1 then
          error("report.md: the {.appendix} heading must be a level-1 heading")
        end
        in_appendix = true
        h.classes = pandoc.List({ "rk-appendix-head" })
        h.level = 2
        return h
      end
      local label
      if in_appendix then
        if h.level == 1 then
          error("report.md: level-1 heading after the appendix: " .. pandoc.utils.stringify(h.content))
        end
        if h.level == 2 then
          appendix_count = appendix_count + 1
          label = "A." .. appendix_count
          table.insert(toc, { id = h.identifier, num = label, title = h.content:clone(), appendix = true })
        end
      elseif h.level == 1 then
        section = section + 1
        sub = 0
        label = tostring(section)
        current = { id = h.identifier, num = label, title = h.content:clone(), children = {} }
        table.insert(toc, current)
      elseif h.level == 2 then
        if current == nil then
          error("report.md: level-2 heading before the first section: " .. pandoc.utils.stringify(h.content))
        end
        sub = sub + 1
        label = section .. "." .. sub
        table.insert(current.children, { id = h.identifier, num = label, title = h.content:clone() })
      end
      if label then
        h.content:insert(1, pandoc.RawInline("html", '<span class="rk-num">' .. label .. "</span>"))
      end
      -- Shifted down one level because the title is the page's only h1.
      h.level = h.level + 1
      return h
    end,
  })

  local function toc_item(entry)
    local s = string.format('<li><a href="#%s"><span class="rk-num">%s</span><span>%s</span></a>',
      entry.id, entry.num, html(entry.title))
    if entry.children and #entry.children > 0 then
      local kids = {}
      for _, c in ipairs(entry.children) do table.insert(kids, toc_item(c)) end
      s = s .. "<ul>" .. table.concat(kids) .. "</ul>"
    end
    return s .. "</li>"
  end
  local main_items, app_items = {}, {}
  for _, e in ipairs(toc) do
    table.insert(e.appendix and app_items or main_items, toc_item(e))
  end

  local has_refs = refs_div ~= nil and #refs_div.content > 0
  local end_items = { '<li><a href="#cite-this">Cite this report</a></li>' }
  if has_refs then table.insert(end_items, '<li><a href="#references">References</a></li>') end
  if #notes > 0 then table.insert(end_items, '<li><a href="#notes">Notes</a></li>') end
  if #assets > 0 then table.insert(end_items, '<li><a href="#data">Data and receipts</a></li>') end

  local toc_html = '<nav class="rk-toc" aria-label="Contents"><p class="rk-toc-head">Contents</p><ul>' ..
    table.concat(main_items) .. "</ul>"
  if #app_items > 0 then
    toc_html = toc_html .. '<p class="rk-toc-head">Appendix</p><ul>' .. table.concat(app_items) .. "</ul>"
  end
  toc_html = toc_html .. '<ul class="rk-toc-end">' .. table.concat(end_items) .. "</ul></nav>"

  local title = meta_string(meta, "title")
  local authors = meta_string(meta, "authors")
  local year = meta_string(meta, "year")
  local revision = meta_string(meta, "revision")
  local url = meta_string(meta, "url")
  local document_id = meta_string(meta, "document_id")

  local bibtex = string.format(
    "@techreport{specter-%s-%s,\n  title = {%s},\n  author = {%s},\n  institution = {Specter Labs},\n  year = {%s},\n  note = {Revision %s},\n  url = {%s}\n}",
    document_id, revision, title, authors, year, revision, url)
  local parts = {
    '<footer class="rk-endmatter">',
    '<section id="cite-this"><h2>Cite this report</h2><p>' ..
      string.format("%s. %s. <em>%s</em>. Specter Labs report, revision %s. %s",
        escape(authors), escape(year), escape(title), escape(revision), escape(url)) ..
      "</p><pre>" .. escape(bibtex) .. "</pre></section>",
  }
  if has_refs then
    table.insert(parts, '<section id="references"><h2>References</h2>' .. html(refs_div.content) .. "</section>")
  end
  if #notes > 0 then
    local items = {}
    for i, content in ipairs(notes) do
      table.insert(items, string.format('<li id="note-%d">%s <a class="rk-back" href="#noteref-%d" aria-label="Back to text">&#8617;&#xFE0E;</a></li>',
        i, inline_note_html(content), i))
    end
    table.insert(parts, '<section id="notes"><h2>Notes</h2><ol class="rk-notes">' .. table.concat(items) .. "</ol></section>")
  end
  if #assets > 0 then
    local items = {}
    for _, a in ipairs(assets) do
      table.insert(items, string.format('<li><a href="%s">%s</a> <span class="rk-path">%s</span></li>',
        escape(a.target), escape(a.text), escape(a.target:gsub("^assets/", ""))))
    end
    table.insert(parts, '<section id="data"><h2>Data and receipts</h2><ul class="rk-data">' .. table.concat(items) .. "</ul></section>")
  end
  table.insert(parts, "</footer>")

  local word_count = select(2, pandoc.utils.stringify(pandoc.Pandoc(body)):gsub("%S+", ""))
    + select(2, pandoc.utils.stringify(meta.abstract):gsub("%S+", ""))
  local minutes = math.max(1, math.floor(word_count / 230 + 0.5))

  meta["rk-toc"] = pandoc.RawInline("html", toc_html)
  meta["rk-endmatter"] = pandoc.RawInline("html", table.concat(parts))
  meta["rk-minutes"] = tostring(minutes)
  meta["pagetitle"] = title .. " | Specter Labs"
  doc.blocks = body
  return doc
end
