-- Crimson Reaper scythe client: input for your own scythe, and effects for every scythe
-- in the server. Lives in StarterPlayer.StarterPlayerScripts.

local CollectionService = game:GetService("CollectionService")
local ContextActionService = game:GetService("ContextActionService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local player = Players.LocalPlayer
local Folder = ReplicatedStorage:WaitForChild("CrimsonScythe")
local Config = require(Folder:WaitForChild("Config"))
local ScytheVFX = require(Folder:WaitForChild("ScytheVFX"))
local Remote = Folder:WaitForChild("Remote")

local TAG = "CrimsonScythe"
local SPECIAL_ACTION = "ScytheSpecial"
local FIRST_PERSON = "ScytheFirstPerson"

local equipped = nil
local combo, lastSwing, lastSpecial = 0, 0, -math.huge
local animCache = {}

-- ---------------------------------------------------------------- your scythe

local function playCustomAnimation(id)
	if not id or id == "" then
		return
	end
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	local animator = humanoid and humanoid:FindFirstChildOfClass("Animator")
	if not animator then
		return
	end
	local track = animCache[id]
	if not track then
		local anim = Instance.new("Animation")
		anim.AnimationId = id
		track = animator:LoadAnimation(anim)
		animCache[id] = track
	end
	track:Play(0.05)
end

local function swing()
	local tool = equipped
	if not tool then
		return
	end
	local now = os.clock()
	if now - lastSwing < Config.Combat.SwingCooldown then
		return
	end
	combo = (now - lastSwing > Config.Combat.ComboReset) and 1 or (combo % 3 + 1)
	lastSwing = now
	playCustomAnimation(Config.Animations.Swing[combo])
	ScytheVFX.Swing(tool, combo)
	Remote:FireServer("Swing", combo)
end

local function special(_, inputState)
	if inputState ~= Enum.UserInputState.Begin then
		return Enum.ContextActionResult.Pass
	end
	local tool = equipped
	if not tool then
		return Enum.ContextActionResult.Pass
	end
	local now = os.clock()
	if now - lastSpecial < Config.Combat.SpecialCooldown then
		return Enum.ContextActionResult.Sink
	end
	lastSpecial = now
	ScytheVFX.SpecialCharge(tool)
	Remote:FireServer("Special")
	task.delay(Config.Combat.SpecialWindup, function()
		if equipped == tool then
			playCustomAnimation(Config.Animations.Special)
			ScytheVFX.SpecialRelease(tool, nil, true)
		end
	end)
	return Enum.ContextActionResult.Sink
end

local hooked = setmetatable({}, { __mode = "k" })

local function hookTool(tool)
	if hooked[tool] or not tool:IsA("Tool") or not CollectionService:HasTag(tool, TAG) then
		return
	end
	hooked[tool] = true
	tool.Equipped:Connect(function()
		equipped = tool
		ContextActionService:BindAction(SPECIAL_ACTION, special, true, table.unpack(Config.SpecialInputs))
		ContextActionService:SetTitle(SPECIAL_ACTION, "Special")
		ContextActionService:SetPosition(SPECIAL_ACTION, UDim2.new(1, -150, 1, -150))
		-- keep the scythe visible in first person (Roblox hides the character there)
		local parts = {}
		for _, d in ipairs(tool:GetDescendants()) do
			if d:IsA("BasePart") then
				table.insert(parts, d)
			end
		end
		RunService:BindToRenderStep(FIRST_PERSON, Enum.RenderPriority.Camera.Value + 2, function()
			for _, p in ipairs(parts) do
				p.LocalTransparencyModifier = 0
			end
		end)
		local handle = tool:FindFirstChild("Handle")
		local sound = handle and handle:FindFirstChild("EquipSound")
		if sound and sound.SoundId ~= "" then
			sound:Play()
		end
	end)
	tool.Unequipped:Connect(function()
		if equipped == tool then
			equipped = nil
		end
		ContextActionService:UnbindAction(SPECIAL_ACTION)
		RunService:UnbindFromRenderStep(FIRST_PERSON)
	end)
	tool.Activated:Connect(swing)
end

local function watch(container)
	for _, child in ipairs(container:GetChildren()) do
		hookTool(child)
	end
	container.ChildAdded:Connect(hookTool)
end

player.ChildAdded:Connect(function(child)
	if child:IsA("Backpack") then
		watch(child)
	end
end)
local backpack = player:FindFirstChildOfClass("Backpack")
if backpack then
	watch(backpack)
end
player.CharacterAdded:Connect(function(character)
	-- dying with the scythe out doesn't always fire Unequipped, so reset here
	equipped = nil
	animCache = {}
	ContextActionService:UnbindAction(SPECIAL_ACTION)
	pcall(function()
		RunService:UnbindFromRenderStep(FIRST_PERSON)
	end)
	watch(character)
end)
if player.Character then
	watch(player.Character)
end

-- ---------------------------------------------------------------- every scythe

local tracked = setmetatable({}, { __mode = "k" })

local function updateIdle(tool)
	local holder = tool.Parent
	local held = holder ~= nil
		and holder:IsA("Model")
		and holder:FindFirstChildOfClass("Humanoid") ~= nil
		and tool:IsDescendantOf(Workspace)
	if held then
		ScytheVFX.StartIdle(tool)
	else
		ScytheVFX.StopIdle(tool)
	end
end

local function trackScythe(tool)
	if tracked[tool] or not tool:IsA("Tool") then
		return
	end
	tracked[tool] = true
	updateIdle(tool)
	tool.AncestryChanged:Connect(function()
		updateIdle(tool)
	end)
end

CollectionService:GetInstanceAddedSignal(TAG):Connect(trackScythe)
CollectionService:GetInstanceRemovedSignal(TAG):Connect(function(tool)
	ScytheVFX.StopIdle(tool)
end)
for _, tool in ipairs(CollectionService:GetTagged(TAG)) do
	trackScythe(tool)
end

-- effects for other players' scythes, and hit impacts for everyone
Remote.OnClientEvent:Connect(function(action, a, b)
	if action == "Impact" and typeof(a) == "Vector3" then
		ScytheVFX.Impact(a, b)
	elseif typeof(a) == "Instance" and a:IsA("Tool") then
		if action == "Swing" then
			ScytheVFX.Swing(a, b)
		elseif action == "SpecialCharge" then
			ScytheVFX.SpecialCharge(a)
		elseif action == "SpecialRelease" then
			ScytheVFX.SpecialRelease(a, b, false)
		end
	end
end)
