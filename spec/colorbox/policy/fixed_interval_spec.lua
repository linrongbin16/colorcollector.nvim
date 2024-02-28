local cwd = vim.fn.getcwd()

describe("policy.fixed_interval", function()
  local assert_eq = assert.is_equal
  local assert_true = assert.is_true
  local assert_false = assert.is_false

  before_each(function()
    vim.api.nvim_command("cd " .. cwd)
  end)

  local strings = require("colorbox.commons.strings")
  local fixed_interval_policy = require("colorbox.policy.fixed_interval")
  require("colorbox").setup({
    debug = true,
    file_log = true,
  })

  describe("[fixed_interval_policy]", function()
    it("is_fixed_interval_policy", function()
      local input1 = {
        seconds = 1,
        implement = "shuffle",
      }
      local actual1 = fixed_interval_policy.is_fixed_interval_policy(input1)
      assert_true(actual1)
      local input2 = {
        seconds = "1",
        implement = nil,
      }
      local actual2 = fixed_interval_policy.is_fixed_interval_policy(input2)
      assert_false(actual2)
    end)
  end)
end)
