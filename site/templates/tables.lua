local function is_number(s)
  return s:gsub("\u{2212}", "-"):gsub(",(%d%d%d)", "%1"):match("^%-?%d+%.?%d*%%?$") ~= nil
end

-- A numeric cell is a number, a range, a count out of a total, or a number
-- followed by a parenthesized number or interval. "·" marks a missing value.
local function is_numeric_cell(s)
  if s == "\u{00B7}" then return true end
  local a, b, c = s:match("^(%S+) %((%S+) to (%S+)%)$")
  if a then return is_number(a) and is_number(b) and is_number(c) end
  a, b = s:match("^(%S+) %((%S+)%)$")
  if a then return is_number(a) and is_number(b) end
  a, b = s:match("^(%S+) to (%S+)$")
  if a then return is_number(a) and is_number(b) end
  a, b = s:match("^(%S+) of (%S+)$")
  if a then return is_number(a) and is_number(b) end
  return is_number(s)
end

-- A narrow numeric column may wrap only before a parenthesized interval, so
-- that a right-aligned "0.002 (-0.006 to 0.010)" breaks into the value and the
-- whole interval rather than mid-interval.
local function keep_value_together(inlines)
  for i, il in ipairs(inlines) do
    local nxt = inlines[i + 1]
    if il.t == "Space" and not (nxt and nxt.t == "Str" and nxt.text:sub(1, 1) == "(") then
      inlines[i] = pandoc.Str("\u{00A0}")
    end
  end
  return inlines
end

-- The parenthesized interval after a value goes in span.ci, which the
-- stylesheet sets on its own muted line, so that every row with an interval
-- reads as estimate over interval rather than as an accidental wrap.
local function set_off_interval(inlines)
  for i, il in ipairs(inlines) do
    local nxt = inlines[i + 1]
    if il.t == "Space" and nxt and nxt.t == "Str" and nxt.text:sub(1, 1) == "(" then
      local interval = pandoc.List()
      for k = i + 1, #inlines do interval:insert(inlines[k]) end
      local out = pandoc.List()
      for k = 1, i do out:insert(inlines[k]) end
      out:insert(pandoc.Span(interval, pandoc.Attr("", { "ci" })))
      return out
    end
  end
  return inlines
end

local function each_cell(rows, fn)
  for _, row in ipairs(rows) do
    local col = 1
    for _, cell in ipairs(row.cells) do
      fn(cell, col)
      col = col + cell.col_span
    end
  end
end

-- A text column whose longest body cell fits in this many characters is
-- marked "short" so that the stylesheet can keep its cells on one line where
-- the table has room, leaving the wrapping to headers and columns of prose.
-- Row labels in the first column get a longer allowance because a wrapped
-- label makes every cell of its row two lines tall.
local SHORT_TEXT, SHORT_LABEL = 24, 32

-- Marks every cell of a column whose body cells are all numeric with the
-- class "num", so that the stylesheet can right-align it and line up digits.
-- Columns the author aligned explicitly are left as written. Column widths are
-- dropped because pandoc divides long pipe tables into equal columns, which
-- squeezes text columns and pads numeric ones.
local function format_table(t)
  local numeric, valued, longest = {}, {}, {}
  for i, spec in ipairs(t.colspecs) do
    numeric[i] = spec[1] == pandoc.AlignDefault
    t.colspecs[i] = { spec[1], pandoc.ColWidthDefault }
  end
  for _, body in ipairs(t.bodies) do
    each_cell(body.body, function(cell, col)
      local text = pandoc.utils.stringify(cell.contents)
      longest[col] = math.max(longest[col] or 0, utf8.len(text))
      if cell.col_span > 1 or not is_numeric_cell(text) then
        for k = col, col + cell.col_span - 1 do numeric[k] = false end
      elseif text ~= "\u{00B7}" then
        valued[col] = true
      end
    end)
  end
  local function mark(cell, col)
    if cell.col_span == 1 and numeric[col] and valued[col] then
      cell.attr.classes:insert("num")
    end
  end
  each_cell(t.head.rows, mark)
  for _, body in ipairs(t.bodies) do
    each_cell(body.body, function(cell, col)
      mark(cell, col)
      if cell.col_span == 1 and not numeric[col] and longest[col] <= (col == 1 and SHORT_LABEL or SHORT_TEXT) then
        cell.attr.classes:insert("short")
      end
      if cell.attr.classes:includes("num") then
        cell.contents = cell.contents:walk({ Inlines = function(inlines)
          return set_off_interval(keep_value_together(inlines))
        end })
      end
    end)
  end
end

-- Tables default to the editorial style; a build that passes
-- table-style=log as metadata gets the denser log style instead.
local wrap_classes = { "table-wrap" }

-- Wide tables scroll inside their own box so that narrow screens keep the
-- page itself from scrolling sideways.
return {
  {
    Meta = function(meta)
      local style = meta["table-style"]
      if style == nil then return end
      style = pandoc.utils.stringify(style)
      if style ~= "log" then error("unknown table-style: " .. style) end
      wrap_classes = { "table-wrap", "log" }
    end,
  },
  {
    Table = function(t)
      format_table(t)
      return pandoc.Div({ t }, pandoc.Attr("", wrap_classes))
    end,
  },
}
