local uv = vim.uv or vim.loop

local M = {}

-- FileLineReader {

--- @class commons.FileLineReader
--- @field filename string    file name.
--- @field handler integer    file handle.
--- @field filesize integer   file size in bytes.
--- @field offset integer     current read position.
--- @field batchsize integer  chunk size for each read operation running internally.
--- @field buffer string?     internal data buffer.
local FileLineReader = {}

--- @param filename string
--- @param batchsize integer?
--- @return commons.FileLineReader?
function FileLineReader:open(filename, batchsize)
  local handler = uv.fs_open(filename, "r", 438) --[[@as integer]]
  if type(handler) ~= "number" then
    error(
      string.format(
        "|commons.fio - FileLineReader:open| failed to fs_open file: %s",
        vim.inspect(filename)
      )
    )
    return nil
  end
  local fstat = uv.fs_fstat(handler) --[[@as table]]
  if type(fstat) ~= "table" then
    error(
      string.format(
        "|commons.fio - FileLineReader:open| failed to fs_fstat file: %s",
        vim.inspect(filename)
      )
    )
    uv.fs_close(handler)
    return nil
  end

  local o = {
    filename = filename,
    handler = handler,
    filesize = fstat.size,
    offset = 0,
    batchsize = batchsize or 4096,
    buffer = nil,
  }
  setmetatable(o, self)
  self.__index = self
  return o
end

--- @private
--- @return integer
function FileLineReader:_read_chunk()
  local chunksize = (self.filesize >= self.offset + self.batchsize) and self.batchsize
    or (self.filesize - self.offset)
  if chunksize <= 0 then
    return 0
  end
  local data, --[[@as string?]]
    read_err,
    read_name =
    uv.fs_read(self.handler, chunksize, self.offset)
  if read_err then
    error(
      string.format(
        "|commons.fio - FileLineReader:_read_chunk| failed to fs_read file: %s, read_error:%s, read_name:%s",
        vim.inspect(self.filename),
        vim.inspect(read_err),
        vim.inspect(read_name)
      )
    )
    return -1
  end
  -- append to buffer
  self.buffer = self.buffer and (self.buffer .. data) or data --[[@as string]]
  self.offset = self.offset + #data
  return #data
end

--- @return boolean
function FileLineReader:has_next()
  self:_read_chunk()
  return self.buffer ~= nil and string.len(self.buffer) > 0
end

--- @return string?
function FileLineReader:next()
  --- @return string?
  local function impl()
    local str = require("colorbox.commons.str")
    if self.buffer == nil then
      return nil
    end
    self.buffer = self.buffer:gsub("\r\n", "\n")
    local nextpos = str.find(self.buffer, "\n")
    if nextpos then
      local line = self.buffer:sub(1, nextpos - 1)
      self.buffer = self.buffer:sub(nextpos + 1)
      return line
    else
      return nil
    end
  end

  repeat
    local nextline = impl()
    if nextline then
      return nextline
    end
  until self:_read_chunk() <= 0

  local nextline = impl()
  if nextline then
    return nextline
  else
    local buf = self.buffer
    self.buffer = nil
    return buf
  end
end

-- Close the file reader.
function FileLineReader:close()
  if self.handler then
    uv.fs_close(self.handler)
    self.handler = nil
  end
end

M.FileLineReader = FileLineReader

-- FileLineReader }

-- CachedFileReader {

--- @class commons.CachedFileReader
--- @field filename string
--- @field cache string?
local CachedFileReader = {}

--- @param filename string
--- @return commons.CachedFileReader
function CachedFileReader:open(filename)
  local o = {
    filename = filename,
    cache = nil,
  }
  setmetatable(o, self)
  self.__index = self
  return o
end

--- @param opts {trim:boolean?}?
--- @return string?
function CachedFileReader:read(opts)
  opts = opts or {}
  opts.trim = type(opts.trim) == "boolean" and opts.trim or false

  if self.cache == nil then
    self.cache = M.readfile(self.filename)
  end
  if self.cache == nil then
    return self.cache
  end
  return opts.trim and vim.trim(self.cache) or self.cache
end

--- @return string?
function CachedFileReader:reset()
  local saved = self.cache
  self.cache = nil
  return saved
end

M.CachedFileReader = CachedFileReader

-- CachedFileReader }

--- @param filename string
--- @param opts {trim:boolean?}?
--- @return string?
M.readfile = function(filename, opts)
  opts = opts or { trim = false }
  opts.trim = type(opts.trim) == "boolean" and opts.trim or false

  local f = io.open(filename, "r")
  if f == nil then
    return nil
  end
  local content = f:read("*a")
  f:close()
  return opts.trim and vim.trim(content) or content
end

--- @alias commons.AsyncReadFileOnComplete fun(data:string?):any
--- @alias commons.AsyncReadFileOnError fun(step:string?,err:string?):any
--- @param filename string
--- @param opts {on_complete:commons.AsyncReadFileOnComplete,on_error:commons.AsyncReadFileOnError?,trim:boolean?}
M.asyncreadfile = function(filename, opts)
  assert(type(opts) == "table")
  assert(type(opts.on_complete) == "function")

  opts.trim = type(opts.trim) == "boolean" and opts.trim or false
  if type(opts.on_error) ~= "function" then
    opts.on_error = function(step1, err1)
      error(
        string.format(
          "failed to read file(%s), filename:%s, error:%s",
          vim.inspect(step1),
          vim.inspect(filename),
          vim.inspect(err1)
        )
      )
    end
  end

  local open_result, open_err = uv.fs_open(filename, "r", 438, function(open_complete_err, fd)
    if open_complete_err then
      opts.on_error("fs_open complete", open_complete_err)
      return
    end
    uv.fs_fstat(fd --[[@as integer]], function(fstat_complete_err, stat)
      if fstat_complete_err then
        opts.on_error("fs_fstat complete", fstat_complete_err)
        return
      end
      if not stat then
        opts.on_error("fs_fstat returns nil", fstat_complete_err)
        return
      end
      uv.fs_read(fd --[[@as integer]], stat.size, 0, function(read_complete_err, data)
        if read_complete_err then
          opts.on_error("fs_read complete", read_complete_err)
          return
        end
        uv.fs_close(fd --[[@as integer]], function(close_complete_err)
          if opts.trim and type(data) == "string" then
            local trimmed_data = vim.trim(data)
            opts.on_complete(trimmed_data)
          else
            opts.on_complete(data)
          end
          if close_complete_err then
            opts.on_error("fs_close complete", close_complete_err)
          end
        end)
      end)
    end)
  end)
  if open_result == nil then
    opts.on_error("fs_open", open_err)
  end
end

--- @param filename string
--- @return string[]|nil
M.readlines = function(filename)
  local ok, reader = pcall(M.FileLineReader.open, M.FileLineReader, filename) --[[@as commons.FileLineReader]]
  if not ok or reader == nil then
    return nil
  end
  local results = {}
  while reader:has_next() do
    table.insert(results, reader:next())
  end
  reader:close()
  return results
end

--- @alias commons.AsyncReadLinesOnLine fun(line:string):any
--- @alias commons.AsyncReadLinesOnComplete fun(bytes:integer):any
--- @alias commons.AsyncReadLinesOnError fun(step:string?,err:string?):any
--- @param filename string
--- @param opts {on_line:commons.AsyncReadLinesOnLine,on_complete:commons.AsyncReadLinesOnComplete,on_error:commons.AsyncReadLinesOnError?,batchsize:integer?}
M.asyncreadlines = function(filename, opts)
  assert(type(opts) == "table")
  assert(type(opts.on_line) == "function")
  local batchsize = opts.batchsize or 4096

  if type(opts.on_error) ~= "function" then
    opts.on_error = function(step1, err1)
      error(
        string.format(
          "failed to async read file by lines(%s), filename:%s, error:%s",
          vim.inspect(step1),
          vim.inspect(filename),
          vim.inspect(err1)
        )
      )
    end
  end

  local open_result, open_err = uv.fs_open(filename, "r", 438, function(open_complete_err, fd)
    if open_complete_err then
      opts.on_error("fs_open complete", open_complete_err)
      return
    end
    local fstat_result, fstat_err = uv.fs_fstat(
      fd --[[@as integer]],
      function(fstat_complete_err, stat)
        if fstat_complete_err then
          opts.on_error("fs_fstat complete", fstat_complete_err)
          return
        end
        if stat == nil then
          opts.on_error("fs_fstat returns nil", fstat_complete_err)
          return
        end

        local fsize = stat.size
        local offset = 0
        local buffer = nil

        local function _process(buf, fn_line_processor)
          local str = require("colorbox.commons.str")

          local i = 1
          while i <= #buf do
            local newline_pos = str.find(buf, "\n", i)
            if not newline_pos then
              break
            end
            local line = buf:sub(i, newline_pos - 1)
            fn_line_processor(line)
            i = newline_pos + 1
          end
          return i
        end

        local function _chunk_read()
          local read_result, read_err = uv.fs_read(
            fd --[[@as integer]],
            batchsize,
            offset,
            function(read_complete_err, data)
              if read_complete_err then
                opts.on_error("fs_read complete", read_complete_err)
                return
              end

              if data then
                offset = offset + #data

                buffer = buffer and (buffer .. data) or data --[[@as string]]
                buffer = buffer:gsub("\r\n", "\n")
                local pos = _process(buffer, opts.on_line)
                -- truncate the processed lines if still exists any
                buffer = pos <= #buffer and buffer:sub(pos, #buffer) or nil
              else
                -- no more data

                -- if buffer still has not been processed
                if buffer then
                  local pos = _process(buffer, opts.on_line)
                  buffer = pos <= #buffer and buffer:sub(pos, #buffer) or nil

                  -- process all the left buffer till the end of file
                  if buffer then
                    opts.on_line(buffer)
                  end
                end

                -- close file
                local close_result, close_err = uv.fs_close(
                  fd --[[@as integer]],
                  function(close_complete_err)
                    if close_complete_err then
                      opts.on_error("fs_close complete", close_complete_err)
                    end
                    if type(opts.on_complete) == "function" then
                      opts.on_complete(fsize)
                    end
                  end
                )
                if close_result == nil then
                  opts.on_error("fs_close", close_err)
                end
              end
            end
          )
          if read_result == nil then
            opts.on_error("fs_read", read_err)
          end
        end

        _chunk_read()
      end
    )

    if fstat_result == nil then
      opts.on_error("fs_fstat", fstat_err)
    end
  end)
  if open_result == nil then
    opts.on_error("fs_open", open_err)
  end
end

-- AsyncFileLineReader }

--- @param filename string  file name.
--- @param content string   file content.
--- @return integer         returns `0` if success, returns `-1` if failed.
M.writefile = function(filename, content)
  local f = io.open(filename, "w")
  if not f then
    return -1
  end
  f:write(content)
  f:close()
  return 0
end

--- @param filename string                      file name.
--- @param content string                       file content.
--- @param on_complete fun(bytes:integer?):any  callback on write complete.
---                                               1. `bytes`: written data bytes.
M.asyncwritefile = function(filename, content, on_complete)
  uv.fs_open(filename, "w", 438, function(open_err, fd)
    if open_err then
      error(
        string.format("failed to open(w) file %s: %s", vim.inspect(filename), vim.inspect(open_err))
      )
      return
    end
    ---@diagnostic disable-next-line: param-type-mismatch
    uv.fs_write(fd, content, nil, function(write_err, bytes)
      if write_err then
        error(
          string.format(
            "failed to write file %s: %s",
            vim.inspect(filename),
            vim.inspect(write_err)
          )
        )
        return
      end
      ---@diagnostic disable-next-line: param-type-mismatch
      uv.fs_close(fd, function(close_err)
        if close_err then
          error(
            string.format(
              "failed to close(w) file %s: %s",
              vim.inspect(filename),
              vim.inspect(close_err)
            )
          )
          return
        end
        if type(on_complete) == "function" then
          on_complete(bytes)
        end
      end)
    end)
  end)
end

--- @param filename string  file name.
--- @param lines string[]   content lines.
--- @return integer         returns `0` if success, returns `-1` if failed.
M.writelines = function(filename, lines)
  local f = io.open(filename, "w")
  if not f then
    return -1
  end
  assert(type(lines) == "table")
  for _, line in ipairs(lines) do
    assert(type(line) == "string")
    f:write(line .. "\n")
  end
  f:close()
  return 0
end

return M
