-- ======================================================================
-- Installer body (SOURCES and LAYOUT are defined above by build_installer.py)
-- ======================================================================

local ChangeHistoryService = game:GetService("ChangeHistoryService")
local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Selection = game:GetService("Selection")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")
local StarterPack = game:GetService("StarterPack")
local StarterPlayer = game:GetService("StarterPlayer")
local Workspace = game:GetService("Workspace")

local TOOL_NAME = "Seraph Blade"
local TAG = "SeraphBlade"
local PARTS = { "Blade", "BladeOrnament", "Guard", "GuardCurls", "Gemstones", "Grip", "GripGold", "Pommel" }
local GOLD = { BladeOrnament = true, Guard = true, GripGold = true, Pommel = true }
local CRYSTAL = { Blade = true, GuardCurls = true, Grip = true }

local notes = {}
local function note(msg)
	table.insert(notes, msg)
	warn("[SeraphBlade] " .. msg)
end

local recording
pcall(function()
	recording = ChangeHistoryService:TryBeginRecording("Install Seraph Blade")
end)

-- ---------------------------------------------------------------- helpers

local function findImport(name)
	for _, inst in ipairs(Selection:Get()) do
		if inst.Name == name then
			return inst
		end
	end
	for _, inst in ipairs(Workspace:GetDescendants()) do
		if inst.Name == name and (inst:IsA("Model") or inst:IsA("Folder")) then
			return inst
		end
	end
	return nil
end

local function findPart(root, name)
	local exact = root:FindFirstChild(name, true)
	if exact and exact:IsA("BasePart") then
		return exact
	end
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("BasePart") and d.Name:sub(1, #name) == name then
			return d
		end
	end
	return nil
end

-- Marker cubes at Blender (0,0,0), (0,1,0), (0,0,1) reveal how the importer scaled / rotated the file.
local function markerFrame(model)
	local o, y, z = findPart(model, "Mark_O"), findPart(model, "Mark_Y"), findPart(model, "Mark_Z")
	assert(o and y and z, model.Name .. ": the Mark_O / Mark_Y / Mark_Z marker parts are missing (re-import the file)")
	local origin = o.Position
	local yv, zv = y.Position - origin, z.Position - origin
	return { O = origin, X = yv.Unit:Cross(zv.Unit), Y = yv.Unit, Z = zv.Unit, k = zv.Magnitude, markers = { o, y, z } }
end

local function toWorld(f, p)
	return f.O + (f.X * p[1] + f.Y * p[2] + f.Z * p[3]) * f.k
end

local function textureOf(part)
	if part:IsA("MeshPart") and part.TextureID ~= "" then
		return part.TextureID
	end
	local sa = part:FindFirstChildOfClass("SurfaceAppearance")
	if sa then
		local ok, id = pcall(function()
			return sa.ColorMap
		end)
		if ok and typeof(id) == "string" and id ~= "" then
			return id
		end
		ok, id = pcall(function()
			return sa.ColorMapContent.Uri
		end)
		if ok and typeof(id) == "string" and id ~= "" then
			return id
		end
	end
	return ""
end

local function clearSurfaceAppearance(part)
	for _, child in ipairs(part:GetChildren()) do
		if child:IsA("SurfaceAppearance") then
			child:Destroy()
		end
	end
end

local function make(className, props, parent)
	local inst = Instance.new(className)
	for k, v in pairs(props) do
		if k ~= "Attributes" then
			inst[k] = v
		end
	end
	for k, v in pairs(props.Attributes or {}) do
		inst:SetAttribute(k, v)
	end
	inst.Parent = parent
	return inst
end

local function ns(points)
	local keys = {}
	for _, p in ipairs(points) do
		table.insert(keys, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(keys)
end

local function upsert(parent, className, name)
	local existing = parent:FindFirstChild(name)
	if existing and existing.ClassName == className then
		return existing
	end
	if existing then
		existing:Destroy()
	end
	return make(className, { Name = name }, parent)
end

local function upsertScript(parent, className, name, source, keepExisting)
	local existing = parent:FindFirstChild(name)
	if existing and keepExisting and existing:IsA(className) then
		return existing
	end
	if existing then
		existing:Destroy()
	end
	local s = Instance.new(className)
	s.Name = name
	s.Source = source
	s.Parent = parent
	return s
end

-- ---------------------------------------------------------------- scripts

local folder = upsert(ReplicatedStorage, "Folder", "SeraphBlade")
local configModule = upsertScript(folder, "ModuleScript", "Config", SOURCES.Config, true)
upsertScript(folder, "ModuleScript", "Layout", SOURCES.Layout, false)
upsertScript(folder, "ModuleScript", "SeraphVFX", SOURCES.SeraphVFX, false)
upsert(folder, "RemoteEvent", "Remote")
upsert(folder, "BindableEvent", "SeraphHit")
local assetsFolder = upsert(folder, "Folder", "Assets")
upsertScript(ServerScriptService, "Script", "SeraphServer", SOURCES.Server, false)
local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
	or make("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, StarterPlayer)
upsertScript(playerScripts, "LocalScript", "SeraphClient", SOURCES.Client, false)

local okConfig, Config = pcall(require, configModule)
if not okConfig then
	note("Config has an error, using defaults for the install: " .. tostring(Config))
	Config = { Sounds = {}, FallbackTextures = {}, VFX = {} }
end
local vfxConfig = Config.VFX or {}

-- ---------------------------------------------------------------- effect textures

local vfxModel = findImport("SeraphVFX")
if vfxModel then
	for key in pairs(assetsFolder:GetAttributes()) do
		assetsFolder:SetAttribute(key, nil)
	end
	local found = 0
	for _, key in ipairs(LAYOUT.textureKeys) do
		local carrier = findPart(vfxModel, "Tex_" .. key)
		local id = carrier and textureOf(carrier) or ""
		if id ~= "" then
			assetsFolder:SetAttribute("Tex_" .. key, id)
			found += 1
		end
	end
	if found < #LAYOUT.textureKeys then
		note(("only %d of %d effect textures came in with the import; missing ones use Roblox's built-in sparkle"):format(
			found,
			#LAYOUT.textureKeys
		))
	end
	vfxModel:Destroy()
else
	note("SeraphVFX not found: import SeraphVFX.fbx (or .glb) to bring in the effect textures, then run this again")
end

local function tex(key)
	local id = assetsFolder:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds"
end

-- ---------------------------------------------------------------- the sword

local model = findImport("SeraphBlade")
local tool

if model then
	local f = markerFrame(model)
	local parts = {}
	for _, name in ipairs(PARTS) do
		parts[name] = findPart(model, name)
		if not parts[name] then
			note("sword part missing: " .. name)
		end
	end
	assert(parts.Grip and parts.Blade, "SeraphBlade is missing its Grip or Blade mesh")

	-- 1 Blender unit = SWORD_SCALE studs, whatever units the importer used
	local factor = LAYOUT.swordScale / f.k
	if math.abs(factor - 1) > 0.01 then
		local all = {}
		for _, p in pairs(parts) do
			table.insert(all, p)
		end
		for _, m in ipairs(f.markers) do
			table.insert(all, m)
		end
		for _, p in ipairs(all) do
			p.Size *= factor
			p.Position = f.O + (p.Position - f.O) * factor
		end
		f = markerFrame(model)
	end

	-- gold keeps its imported textures (polished, with the engraved filigree); the white crystal
	-- and the diamonds get their styles from Config
	for name, p in pairs(parts) do
		p.CastShadow = GOLD[name] == true
		if GOLD[name] then
			p.Material = Enum.Material.Metal
			if textureOf(p) == "" then
				p:SetAttribute("ColorKey", "Gold")
			end
		else
			p:SetAttribute("CrystalTexture", textureOf(p))
			clearSurfaceAppearance(p)
			if CRYSTAL[name] then
				p:SetAttribute("Crystal", true)
				p:SetAttribute("ColorKey", "Crystal")
			else
				p:SetAttribute("Gem", true)
				p:SetAttribute("ColorKey", "Gem")
			end
		end
	end

	for _, container in ipairs({ StarterPack, ServerStorage }) do
		local old = container:FindFirstChild(TOOL_NAME)
		if old then
			old:Destroy()
		end
	end
	tool = make("Tool", {
		Name = TOOL_NAME,
		ToolTip = "Click: radiant slash combo  |  E: Heaven's Verdict",
		CanBeDropped = false,
		RequiresHandle = true,
		Attributes = { SeraphScale = LAYOUT.swordScale },
	}, nil)
	CollectionService:AddTag(tool, TAG)

	local handle = parts.Grip
	handle.Name = "Handle"
	local s = LAYOUT.swordScale
	local P = LAYOUT.points
	-- invisible volumes along the blade and round the guard, for their motes and sparkles
	local vol = LAYOUT.bladeVolume
	local fxBlade = make("Part", {
		Name = "FXBlade",
		Transparency = 1,
		Size = Vector3.new(vol.size[1], vol.size[3], vol.size[2]) * s,
		CFrame = CFrame.fromMatrix(toWorld(f, vol.centre), f.X, f.Z),
	}, model)
	local fxGuard = make("Part", {
		Name = "FXGuard",
		Transparency = 1,
		Size = Vector3.new(1.0 * s, 0.7 * s, 0.4 * s),
		CFrame = CFrame.fromMatrix(toWorld(f, P.Gem), f.X, f.Z),
	}, model)
	parts.FXBlade, parts.FXGuard = fxBlade, fxGuard

	for _, p in pairs(parts) do
		p.Anchored = false
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.Massless = true
		p.Parent = tool
	end
	for _, p in pairs(parts) do
		if p ~= handle then
			make("WeldConstraint", { Part0 = handle, Part1 = p }, handle)
		end
	end

	-- Grip: the hand round the grip, the blade up the hand's grip axis (like the other swords).
	-- GRIP_TILT / GRIP_SPIN fine-tune it.
	local gripPos = handle.CFrame:PointToObjectSpace(toWorld(f, P.Grip))
	tool.Grip = CFrame.fromMatrix(
		gripPos,
		handle.CFrame:VectorToObjectSpace(f.X),
		handle.CFrame:VectorToObjectSpace(-f.Z)
	) * CFrame.Angles(math.rad(GRIP_TILT), math.rad(GRIP_SPIN), 0)

	local function attach(part, name, point)
		local a = make("Attachment", { Name = name }, part)
		a.WorldCFrame = CFrame.fromMatrix(toWorld(f, point), f.X, f.Z)
		return a
	end
	attach(handle, "Origin", { 0, 0, 0 })
	local aGem = attach(handle, "Gem", P.Gem)
	local aPommel = attach(handle, "Pommel", P.Pommel)
	local aTrailBase = attach(fxBlade, "TrailBase", P.TrailBase)
	local aTip = attach(fxBlade, "BladeTip", P.BladeTip)

	-- the energy ribbons: white strands and thinner gold ones swirling round the blade (chains
	-- of curved camera-facing beams whose texture scrolls, so the light keeps flowing)
	local auraOn = vfxConfig.Aura ~= false
	local flow = vfxConfig.AuraSpeed or 0.5
	local function auraChain(name, nodes, widthFn, props, parent)
		local atts = {}
		for i, p in ipairs(nodes) do
			local prev, nxt = nodes[math.max(1, i - 1)], nodes[math.min(#nodes, i + 1)]
			local t = (toWorld(f, nxt) - toWorld(f, prev)).Unit
			local up = math.abs(t:Dot(f.Y)) > 0.95 and f.X or f.Y
			atts[i] = make("Attachment", { Name = name .. i }, parent)
			atts[i].WorldCFrame = CFrame.fromMatrix(toWorld(f, p), t, (up - t * up:Dot(t)).Unit)
		end
		for i = 1, #atts - 1 do
			local a0, a1 = atts[i], atts[i + 1]
			local handleLength = (a1.WorldPosition - a0.WorldPosition).Magnitude / 3
			local beamProps = {
				Name = name,
				Attachment0 = a0,
				Attachment1 = a1,
				TextureMode = Enum.TextureMode.Wrap,
				TextureLength = 1.4 * s,
				CurveSize0 = handleLength,
				CurveSize1 = handleLength,
				Segments = 8,
				FaceCamera = true,
				LightInfluence = 0,
				Width0 = widthFn((i - 1) / (#atts - 1)) * s,
				Width1 = widthFn(i / (#atts - 1)) * s,
				Enabled = auraOn,
			}
			for k, v in pairs(props) do
				beamProps[k] = v
			end
			make("Beam", beamProps, parent)
		end
	end
	local function every(list, step)
		local out = {}
		for i = 1, #list, step do
			table.insert(out, list[i])
		end
		if out[#out] ~= list[#list] then
			table.insert(out, list[#list])
		end
		return out
	end
	for i, path in ipairs(LAYOUT.ribbons) do
		local wmax = LAYOUT.ribbonWidths[i]
		local key = LAYOUT.ribbonGold[i] and "RibbonGold" or "Ribbon"
		auraChain("EnergyRibbon" .. i, every(path, 4), function(t)
			return 0.012 + wmax * 1.5 * math.sin(math.pi * t) ^ 0.8
		end, {
			Texture = tex(key),
			TextureSpeed = -flow,
			LightEmission = 1,
			Transparency = NumberSequence.new(0.2),
			ZOffset = 0.1,
			Attributes = { TextureKey = key, Aura = true },
		}, handle)
	end

	-- white aura (the main light), gold aura (the softer secondary glow), a halo and light rays
	-- behind the guard, star flashes and tiny motes
	local box = Enum.ParticleEmitterShape.Box
	local volume = Enum.ParticleEmitterShapeStyle.Volume
	local still = NumberRange.new(0)
	local function glowProps(name, key, size, transparency, z)
		return {
			Name = name,
			Texture = tex(key),
			Rate = 2,
			Lifetime = NumberRange.new(1.0),
			Speed = still,
			LockedToPart = true,
			Size = ns({ { 0, size * 0.92 * s }, { 0.5, size * s }, { 1, size * 0.92 * s } }),
			Transparency = ns({ { 0, 1 }, { 0.3, transparency }, { 0.7, transparency }, { 1, 1 } }),
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = z,
			Attributes = { TextureKey = key },
		}
	end
	make("ParticleEmitter", glowProps("WhiteAura", "GlowWhite", 1.0, 0.55, -0.2), aGem)
	make("ParticleEmitter", glowProps("GoldAura", "GlowGold", 1.45, 0.72, -0.3), aGem)
	make("ParticleEmitter", glowProps("GoldAura", "GlowGold", 0.42, 0.65, -0.1), aPommel)
	local halo = glowProps("Halo", "Halo", 0.8, 0.45, -0.25)
	halo.RotSpeed = NumberRange.new(-10, 10)
	make("ParticleEmitter", halo, aGem)
	local rays = glowProps("LightRays", "Rays", 1.4, 0.7, -0.35)
	rays.Rotation = NumberRange.new(0, 360)
	rays.RotSpeed = NumberRange.new(-12, 12)
	make("ParticleEmitter", rays, aGem)
	make("Beam", {
		Name = "WhiteAura",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("GlowWhite"),
		TextureMode = Enum.TextureMode.Stretch,
		Width0 = 0.55 * s,
		Width1 = 0.2 * s,
		FaceCamera = true,
		LightEmission = 1,
		LightInfluence = 0,
		Transparency = NumberSequence.new(0.7),
		ZOffset = -0.2,
		Attributes = { TextureKey = "GlowWhite" },
	}, fxBlade)
	make("Beam", {
		Name = "GoldAura",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("GlowGold"),
		TextureMode = Enum.TextureMode.Stretch,
		Width0 = 0.85 * s,
		Width1 = 0.3 * s,
		FaceCamera = true,
		LightEmission = 1,
		LightInfluence = 0,
		Transparency = NumberSequence.new(0.8),
		ZOffset = -0.3,
		Attributes = { TextureKey = "GlowGold" },
	}, fxBlade)
	for _, part in ipairs({ fxBlade, fxGuard }) do
		local big = part == fxGuard
		make("ParticleEmitter", {
			Name = "Sparkles",
			Texture = tex("Sparkle"),
			Shape = box,
			ShapeStyle = volume,
			Rate = big and 2.5 or 2,
			Lifetime = NumberRange.new(0.4, 0.7),
			Speed = still,
			Rotation = NumberRange.new(0, 45),
			Size = ns({ { 0, 0 }, { 0.4, (big and 0.16 or 0.12) * s }, { 1, 0 } }),
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = 0.4,
			Attributes = { TextureKey = "Sparkle" },
		}, part)
		make("ParticleEmitter", {
			Name = "Particles",
			Texture = tex("Mote"),
			Shape = box,
			ShapeStyle = volume,
			Rate = big and 4 or 6,
			Lifetime = NumberRange.new(1.0, 1.6),
			Speed = NumberRange.new(0.1, 0.3),
			SpreadAngle = Vector2.new(180, 180),
			Acceleration = Vector3.new(0, 0.4, 0),
			Size = ns({ { 0, 0 }, { 0.2, 0.05 * s }, { 1, 0 } }),
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = 0.3,
			Attributes = { TextureKey = "Mote" },
		}, part)
	end
	make("PointLight", {
		Name = "GemLight",
		Range = 9 * s,
		Brightness = 1.5,
		Shadows = false,
		Attributes = { ColorKey = "Light" },
	}, aGem)
	make("ParticleEmitter", {
		Name = "SwingSparkles",
		Texture = tex("Sparkle"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 0,
		Lifetime = NumberRange.new(0.3, 0.55),
		Speed = NumberRange.new(4, 9),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 5,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0.28 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { TextureKey = "Sparkle" },
	}, fxBlade)

	-- swing trails along the blade
	make("Trail", {
		Name = "SwingTrail",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("Trail"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.2,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 0.9,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Trail", SwingTrail = true },
	}, fxBlade)
	make("Trail", {
		Name = "SwingGlow",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("GlowWhite"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.28,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0.5 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "GlowWhite", SwingTrail = true },
	}, fxBlade)

	local sounds = Config.Sounds or {}
	for name, loudness in pairs({ Equip = 0.5, Swing = 0.6, Special = 0.8 }) do
		make("Sound", { Name = name .. "Sound", SoundId = sounds[name] or "", Volume = loudness }, handle)
	end

	for _, m in ipairs(f.markers) do
		m:Destroy()
	end
	model:Destroy()

	tool.Parent = StarterPack
	local copy = tool:Clone()
	copy.Parent = ServerStorage
	local okVfx, VFX = pcall(require, folder:FindFirstChild("SeraphVFX"))
	if okVfx then
		VFX.ApplyColors(tool)
		VFX.ApplyColors(copy)
	else
		note("could not preview the colours in Studio (" .. tostring(VFX) .. "); they apply in game")
	end
	Selection:Set({ tool })
else
	tool = StarterPack:FindFirstChild(TOOL_NAME)
	if tool then
		note("SeraphBlade not found, so only the scripts were updated (the existing sword was kept)")
	else
		note("SeraphBlade not found: import SeraphBlade.fbx (or .glb) with the 3D Importer, then run this again")
	end
end

if recording then
	pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
end

print(("[SeraphBlade] Install finished%s. Sword: %s | Scripts: ReplicatedStorage.SeraphBlade, "):format(
	#notes > 0 and (" with " .. #notes .. " note(s) above") or "",
	tool and tool:GetFullName() or "not built"
) .. "ServerScriptService.SeraphServer, StarterPlayerScripts.SeraphClient")
