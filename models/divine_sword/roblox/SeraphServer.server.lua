-- Seraph Blade server: hit detection, damage, cooldowns, and telling other
-- players to play the effects. Lives in ServerScriptService.
--
-- Hook it into your game: ReplicatedStorage.SeraphBlade.SeraphHit (BindableEvent)
-- fires (attackerPlayer, hitInstance, damage, isSpecial) for every hit. Tag any
-- part or model "SwordHittable" (e.g. balloons) to make the sword hit it too
-- (the same tag the other swords use).

local CollectionService = game:GetService("CollectionService")
local Debris = game:GetService("Debris")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Folder = ReplicatedStorage:WaitForChild("SeraphBlade")
local Config = require(Folder:WaitForChild("Config"))
local SeraphVFX = require(Folder:WaitForChild("SeraphVFX"))
local Remote = Folder:WaitForChild("Remote")
local SeraphHit = Folder:WaitForChild("SeraphHit")

local TAG = "SeraphBlade"
local HITTABLE = "SwordHittable"

-- ---------------------------------------------------------------- tool setup

local setUp = setmetatable({}, { __mode = "k" })

local function setupTool(tool)
	if setUp[tool] or not tool:IsA("Tool") then
		return
	end
	setUp[tool] = true
	local handle = tool:FindFirstChild("Handle")
	if handle then
		-- make sure every mesh is welded (the installer does this, but be safe)
		local welded = { [handle] = true }
		for _, w in ipairs(tool:GetDescendants()) do
			if w:IsA("WeldConstraint") or w:IsA("Weld") then
				if w.Part0 then
					welded[w.Part0] = true
				end
				if w.Part1 then
					welded[w.Part1] = true
				end
			end
		end
		for _, part in ipairs(tool:GetDescendants()) do
			if part:IsA("BasePart") then
				part.Anchored = false
				part.CanCollide = false
				part.Massless = true
				if not welded[part] then
					local w = Instance.new("WeldConstraint")
					w.Part0 = handle
					w.Part1 = part
					w.Parent = handle
				end
			end
		end
	end
	SeraphVFX.ApplyColors(tool)
end

CollectionService:GetInstanceAddedSignal(TAG):Connect(setupTool)
for _, tool in ipairs(CollectionService:GetTagged(TAG)) do
	setupTool(tool)
end

-- ---------------------------------------------------------------- combat

local state = {}

Players.PlayerRemoving:Connect(function(player)
	state[player] = nil
end)

local function equippedSword(player)
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if not humanoid or humanoid.Health <= 0 then
		return nil
	end
	for _, child in ipairs(character:GetChildren()) do
		if child:IsA("Tool") and CollectionService:HasTag(child, TAG) then
			return child, character
		end
	end
	return nil
end

local function fireOthers(player, ...)
	for _, other in ipairs(Players:GetPlayers()) do
		if other ~= player then
			Remote:FireClient(other, ...)
		end
	end
end

-- Roblox's default Animate script plays its tool slash / lunge when it sees this value.
local function playToolAnim(tool, name)
	if name == "Slash" and #Config.Animations.Swing > 0 then
		return
	end
	if name == "Lunge" and Config.Animations.Special ~= "" then
		return
	end
	local value = Instance.new("StringValue")
	value.Name = "toolanim"
	value.Value = name
	value.Parent = tool
	Debris:AddItem(value, 2)
end

local function sameTeam(a, b)
	if Config.Combat.FriendlyFire or not (a and b) then
		return false
	end
	return a.Team ~= nil and a.Team == b.Team and not a.Neutral
end

local function doHits(player, character, tool, isSpecial, combo)
	local root = character:FindFirstChild("HumanoidRootPart")
	if not root or tool.Parent ~= character then
		return
	end
	local c = Config.Combat
	-- swings sweep the area in front; the special (Heaven's Verdict) strikes all the way round
	local box, size
	if isSpecial then
		box = root.CFrame * CFrame.new(0, 0.5, 0)
		size = Vector3.new(c.SpecialRadius * 2, 9, c.SpecialRadius * 2)
	else
		box = root.CFrame * CFrame.new(0, 0.5, -c.SwingRange / 2)
		size = Vector3.new(c.SwingWidth, c.SwingHeight, c.SwingRange)
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { character }
	local damage = isSpecial and c.SpecialDamage or (c.SwingDamage[combo] or c.SwingDamage[1])
	local hitModels, hitThings = {}, {}
	for _, part in ipairs(Workspace:GetPartBoundsInBox(box, size, params)) do
		local model = part:FindFirstAncestorOfClass("Model")
		local humanoid = model and model:FindFirstChildOfClass("Humanoid")
		if humanoid then
			if not hitModels[model] and humanoid.Health > 0 then
				hitModels[model] = true
				local victim = Players:GetPlayerFromCharacter(model)
				if not sameTeam(player, victim) then
					if c.DamageHumanoids then
						humanoid:TakeDamage(damage)
					end
					local target = model:FindFirstChild("HumanoidRootPart") or part
					Remote:FireAllClients("Impact", target.Position, isSpecial)
					SeraphHit:Fire(player, model, damage, isSpecial)
				end
			end
		else
			local thing = CollectionService:HasTag(part, HITTABLE) and part
				or (model and CollectionService:HasTag(model, HITTABLE) and model)
			if thing and not hitThings[thing] then
				hitThings[thing] = true
				Remote:FireAllClients("Impact", part.Position, isSpecial)
				SeraphHit:Fire(player, thing, damage, isSpecial)
			end
		end
	end
end

Remote.OnServerEvent:Connect(function(player, action, combo)
	local tool, character = equippedSword(player)
	if not tool then
		return
	end
	local st = state[player]
	if not st then
		st = { lastSwing = 0, lastSpecial = -math.huge }
		state[player] = st
	end
	local now = os.clock()
	if action == "Swing" then
		-- a little leeway for network jitter
		if now - st.lastSwing < Config.Combat.SwingCooldown * 0.8 then
			return
		end
		st.lastSwing = now
		combo = math.floor(tonumber(combo) or 1)
		if combo ~= combo then
			combo = 1
		end
		combo = math.clamp(combo, 1, 3)
		playToolAnim(tool, "Slash")
		fireOthers(player, "Swing", tool, combo)
		task.delay(Config.Combat.HitDelay, function()
			doHits(player, character, tool, false, combo)
		end)
	elseif action == "Special" then
		if now - st.lastSpecial < Config.Combat.SpecialCooldown * 0.9 then
			return
		end
		st.lastSpecial = now
		fireOthers(player, "SpecialCharge", tool)
		task.delay(Config.Combat.SpecialWindup, function()
			if tool.Parent ~= character then
				return
			end
			playToolAnim(tool, "Lunge")
			fireOthers(player, "SpecialRelease", tool, SeraphVFX.ComputeImpact(character))
			doHits(player, character, tool, true, 1)
		end)
	end
end)
