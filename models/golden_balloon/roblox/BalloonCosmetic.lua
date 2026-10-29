-- Golden King Balloon: equip / attach API and the look (styles, colours, textures).
-- Lives in ReplicatedStorage.GoldenKingBalloon.BalloonCosmetic.
--
-- Server:
--   local Balloon = require(ReplicatedStorage.GoldenKingBalloon.BalloonCosmetic)
--   Balloon.Equip(player)      -- wears it now and after every respawn
--   Balloon.Unequip(player)
--   Balloon.IsEquipped(player)
-- Anywhere (e.g. a shop ViewportFrame):
--   local model = Balloon.Clone()   -- a fresh, anchored copy to show

local CollectionService = game:GetService("CollectionService")
local Players = game:GetService("Players")

local Folder = script.Parent
local Config = require(Folder:WaitForChild("Config"))

local Balloon = {}

Balloon.NAME = "GoldenKingBalloon"
Balloon.TAG = "GoldenKingBalloon" -- CollectionService tag on every worn balloon (the client animates these)

-- ---------------------------------------------------------------- looks

local function assets()
	return Folder:FindFirstChild("Assets")
end

-- Texture id for an effect key, and true when it had to fall back to a built-in texture.
function Balloon.Texture(key)
	local override = Config.Textures and Config.Textures[key]
	if override and override ~= "" then
		return override, false
	end
	local a = assets()
	local id = a and a:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id, false
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds", true
end

local function hasSurfaceAppearance(part)
	return part:FindFirstChildOfClass("SurfaceAppearance") ~= nil
end

-- The Glow style hides the imported SurfaceAppearance in a folder (so it can come back).
local function stashFolder(part)
	local f = part:FindFirstChild("Stash")
	if not f then
		f = Instance.new("Folder")
		f.Name = "Stash"
		f.Parent = part
	end
	return f
end

local function styleBalloon(part)
	if Config.BalloonStyle == "Glow" then
		part.Material = Enum.Material.Neon
		part.Color = Config.Colors.Balloon
		local sa = part:FindFirstChildOfClass("SurfaceAppearance")
		if sa then
			sa.Parent = stashFolder(part)
		end
		return
	end
	local stash = part:FindFirstChild("Stash")
	local sa = stash and stash:FindFirstChildOfClass("SurfaceAppearance")
	if sa then
		sa.Parent = part
	end
	if hasSurfaceAppearance(part) then
		part.Material = Enum.Material.SmoothPlastic
	else
		-- no PBR maps came in with the import: a glossy plastic over the painted gold texture
		part.Material = Enum.Material.SmoothPlastic
		part.Reflectance = 0.12
		if part.TextureID == "" then
			part.Color = Config.Colors.Balloon
		end
	end
end

local function styleGem(part)
	local style = Config.GemStyle or "Glass"
	local texture = part:GetAttribute("GemTexture") or ""
	part.Color = Config.Colors.Gem
	if style == "Neon" then
		part.Material = Enum.Material.Neon
		part.TextureID = ""
		part.Transparency = 0
	elseif style == "Texture" then
		part.Material = Enum.Material.SmoothPlastic
		part.TextureID = texture
		part.Transparency = 0
	else
		part.Material = Enum.Material.Glass
		part.TextureID = texture
		part.Transparency = Config.GemTransparency or 0.12
	end
end

local function styleFeather(part)
	local texture = part:GetAttribute("FeatherTexture") or ""
	if Config.WingStyle == "Glow" then
		part.Material = Enum.Material.Neon
		part.Color = Config.Colors.Feather
		part.TextureID = ""
	else
		part.Material = Enum.Material.SmoothPlastic
		part.TextureID = texture
		part.Color = texture ~= "" and Color3.new(1, 1, 1) or Config.Colors.Feather
	end
end

-- Applies Config (styles, colours, texture overrides, aura switches) to a balloon model.
function Balloon.ApplyStyle(model)
	local vfx = Config.VFX or {}
	local auraOn = vfx.Aura ~= false
	for _, inst in ipairs(model:GetDescendants()) do
		local kind = inst:GetAttribute("Kind")
		if inst:IsA("BasePart") and kind then
			if kind == "Balloon" then
				styleBalloon(inst)
			elseif kind == "Gem" then
				styleGem(inst)
			elseif kind == "Feather" then
				styleFeather(inst)
			elseif kind == "Gold" and not hasSurfaceAppearance(inst) and inst.TextureID == "" then
				inst.Color = Config.Colors.Gold
			elseif kind == "String" then
				inst.Color = Config.Colors.String
				inst.Transparency = Config.TetherToHand and 1 or 0
			end
		end
		local colorKey = inst:GetAttribute("ColorKey")
		if colorKey and Config.Colors[colorKey] and inst:IsA("Light") then
			inst.Color = Config.Colors[colorKey]
		end
		local key = inst:GetAttribute("TextureKey")
		if key and (inst:IsA("ParticleEmitter") or inst:IsA("Trail") or inst:IsA("Beam")) then
			inst.Texture = Balloon.Texture(key)
			local group = inst:GetAttribute("Group")
			local on = auraOn
			if group == "Trails" then
				on = on and vfx.Trails ~= false
			elseif group == "Feathers" then
				on = on and vfx.Feathers ~= false
			end
			inst.Enabled = on
			if inst:IsA("Beam") then
				inst.TextureSpeed = (inst:GetAttribute("FlowSign") or -1) * (vfx.TrailFlow or 0.5)
			end
		end
		if inst:IsA("PointLight") then
			inst.Enabled = auraOn
		end
	end
end

-- ---------------------------------------------------------------- attaching to a character

local function template()
	local t = Folder:FindFirstChild(Balloon.NAME)
	assert(t and t:IsA("Model"), "ReplicatedStorage.GoldenKingBalloon." .. Balloon.NAME .. " is missing (run the installer)")
	return t
end

-- A fresh copy of the balloon (anchored, not tagged), e.g. for a shop ViewportFrame.
function Balloon.Clone()
	local model = template():Clone()
	Balloon.ApplyStyle(model)
	return model
end

-- How much taller or shorter an R15 character is than the default (1 for R6).
local function heightScale(character)
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	local root = character:FindFirstChild("HumanoidRootPart")
	if humanoid and root and humanoid.RigType == Enum.HumanoidRigType.R15 then
		return math.clamp((humanoid.HipHeight + root.Size.Y / 2) / 3, 0.4, 3)
	end
	return 1
end

function Balloon.Detach(character)
	local existing = character and character:FindFirstChild(Balloon.NAME)
	if existing then
		existing:Destroy()
	end
end

-- Puts the balloon on a character (server). Returns the model.
function Balloon.Attach(character)
	local root = character:WaitForChild("HumanoidRootPart", 10)
	local humanoid = character:FindFirstChildOfClass("Humanoid") or character:WaitForChild("Humanoid", 5)
	if not root then
		return nil
	end
	Balloon.Detach(character)
	local model = template():Clone()
	model.Name = Balloon.NAME
	local balloon = model.PrimaryPart or model:FindFirstChild("Balloon")
	for _, p in ipairs(model:GetDescendants()) do
		if p:IsA("BasePart") then
			p.Anchored = false
			p.CanCollide = false
			p.CanQuery = false
			p.CanTouch = false
			p.Massless = true
		end
	end
	local offset = Config.Offset * heightScale(character)
	local weld = Instance.new("Weld")
	weld.Name = "BalloonWeld"
	weld.Part0 = root
	weld.Part1 = balloon
	weld.C0 = CFrame.new(offset)
	weld.C1 = balloon.PivotOffset
	weld:SetAttribute("Offset", offset)
	model:PivotTo(root.CFrame * weld.C0)
	weld.Parent = balloon

	if Config.TetherToHand then
		local hand = character:FindFirstChild("RightHand") or character:FindFirstChild("Right Arm")
		local handAtt = hand and (hand:FindFirstChild("RightGripAttachment") or hand:FindFirstChildOfClass("Attachment"))
		local nozzle = balloon:FindFirstChild("Nozzle")
		if handAtt and nozzle then
			local beam = Instance.new("Beam")
			beam.Name = "Tether"
			beam.Attachment0 = nozzle
			beam.Attachment1 = handAtt
			beam.Width0, beam.Width1 = 0.06, 0.05
			beam.Color = ColorSequence.new(Config.Colors.String)
			beam.LightInfluence = 0.6
			beam.Segments = 16
			beam.CurveSize0 = -1.2
			beam.CurveSize1 = 0.6
			beam.FaceCamera = true
			beam.Parent = balloon
		end
	end

	Balloon.ApplyStyle(model)
	local owner = Players:GetPlayerFromCharacter(character)
	model:SetAttribute("OwnerUserId", owner and owner.UserId or 0)
	CollectionService:AddTag(model, Balloon.TAG)
	model.Parent = character

	-- when its player dies the balloon lets go: the client floats it up and away
	if humanoid then
		humanoid.Died:Once(function()
			if not model.Parent then
				return
			end
			if (Config.Float or {}).FloatAwayOnDeath ~= false then
				weld:Destroy() -- let go of the player before anchoring, so the body isn't held up
				for _, p in ipairs(model:GetDescendants()) do
					if p:IsA("BasePart") then
						p.Anchored = true
					end
				end
				model:SetAttribute("Released", workspace:GetServerTimeNow())
				task.delay(5, function()
					if model.Parent then
						model:Destroy()
					end
				end)
			end
		end)
	end
	return model
end

-- ---------------------------------------------------------------- equipping players

function Balloon.IsEquipped(player)
	return player:GetAttribute(Config.EquipAttribute) == Balloon.NAME
end

function Balloon.Equip(player)
	player:SetAttribute(Config.EquipAttribute, Balloon.NAME)
	if player.Character then
		Balloon.Attach(player.Character)
	end
end

function Balloon.Unequip(player)
	if Balloon.IsEquipped(player) then
		player:SetAttribute(Config.EquipAttribute, nil)
	end
	Balloon.Detach(player.Character)
end

return Balloon
