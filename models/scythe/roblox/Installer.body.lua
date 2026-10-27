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

local TOOL_NAME = "Crimson Reaper"
local TAG = "CrimsonScythe"
local PARTS = { "Shaft", "HeadArmor", "Blade", "Crystals", "Core", "Glow" }
local METAL = { Shaft = true, HeadArmor = true }
local CRYSTAL = { Blade = true, Crystals = true, Core = true }

local notes = {}
local function note(msg)
	table.insert(notes, msg)
	warn("[CrimsonReaper] " .. msg)
end

local recording
pcall(function()
	recording = ChangeHistoryService:TryBeginRecording("Install Crimson Reaper")
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

local folder = upsert(ReplicatedStorage, "Folder", "CrimsonScythe")
local configModule = upsertScript(folder, "ModuleScript", "Config", SOURCES.Config, true)
upsertScript(folder, "ModuleScript", "Layout", SOURCES.Layout, false)
upsertScript(folder, "ModuleScript", "ScytheVFX", SOURCES.ScytheVFX, false)
upsert(folder, "RemoteEvent", "Remote")
upsert(folder, "BindableEvent", "ScytheHit")
local assetsFolder = upsert(folder, "Folder", "Assets")
upsertScript(ServerScriptService, "Script", "ScytheServer", SOURCES.Server, false)
local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
	or make("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, StarterPlayer)
upsertScript(playerScripts, "LocalScript", "ScytheClient", SOURCES.Client, false)

local okConfig, Config = pcall(require, configModule)
if not okConfig then
	note("Config has an error, using defaults for the install: " .. tostring(Config))
	Config = { Sounds = {}, FallbackTextures = {}, VFX = {} }
end
local vfxConfig = Config.VFX or {}

-- ---------------------------------------------------------------- effect textures

local vfxModel = findImport("ScytheVFX")
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
	note("ScytheVFX not found: import ScytheVFX.fbx (or .glb) to bring in the effect textures, then run this again")
end

local function tex(key)
	local id = assetsFolder:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds"
end

-- ---------------------------------------------------------------- the scythe

local model = findImport("Scythe")
local tool

if model then
	local f = markerFrame(model)
	local parts = {}
	for _, name in ipairs(PARTS) do
		parts[name] = findPart(model, name)
		if not parts[name] then
			note("scythe part missing: " .. name)
		end
	end
	assert(parts.Shaft, "Scythe is missing its Shaft mesh")

	-- 1 Blender unit = SCYTHE_SCALE studs, whatever units the importer used
	local factor = LAYOUT.scytheScale / f.k
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

	-- black metal keeps its imported texture; crystals get the crystal style; the glow is Neon
	for name, p in pairs(parts) do
		p.CastShadow = METAL[name] == true
		if METAL[name] then
			p.Material = Enum.Material.Metal
			if textureOf(p) == "" then
				p:SetAttribute("ColorKey", "Metal")
			end
		elseif CRYSTAL[name] then
			p:SetAttribute("CrystalTexture", textureOf(p))
			clearSurfaceAppearance(p)
			p:SetAttribute("Crystal", true)
			p:SetAttribute("ColorKey", "Crystal")
		else
			clearSurfaceAppearance(p)
			if p:IsA("MeshPart") then
				p.TextureID = ""
			end
			p.Material = Enum.Material.Neon
			p:SetAttribute("ColorKey", "Glow")
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
		ToolTip = "Click: reap combo  |  E: Crimson Reap",
		CanBeDropped = false,
		RequiresHandle = true,
		Attributes = { ScytheScale = LAYOUT.scytheScale },
	}, nil)
	CollectionService:AddTag(tool, TAG)

	local handle = parts.Shaft
	handle.Name = "Handle"
	local s = LAYOUT.scytheScale
	local P = LAYOUT.points
	-- invisible volume along the shaft, for the shaft's smoke and sparks
	local shaftTop, shaftBottom = toWorld(f, P.ShaftTop), toWorld(f, P.ShaftBottom)
	local fxShaft = make("Part", {
		Name = "FXShaft",
		Transparency = 1,
		Size = Vector3.new(0.3 * s, (shaftTop - shaftBottom).Magnitude, 0.3 * s),
		CFrame = CFrame.fromMatrix((shaftTop + shaftBottom) / 2, f.X, f.Z),
	}, model)
	parts.FXShaft = fxShaft

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

	-- Grip: the hand round the lower shaft. GRIP_TILT turns the shaft up from "pointing ahead
	-- like a sword"; GRIP_SPIN turns the blade round the shaft.
	local gripPos = handle.CFrame:PointToObjectSpace(toWorld(f, P.Grip))
	tool.Grip = CFrame.fromMatrix(
		gripPos,
		handle.CFrame:VectorToObjectSpace(f.X),
		handle.CFrame:VectorToObjectSpace(f.Z)
	) * CFrame.Angles(math.rad(GRIP_TILT), math.rad(GRIP_SPIN), 0)

	local function attach(part, name, point, axis)
		local a = make("Attachment", { Name = name }, part)
		local world = toWorld(f, point)
		if axis then
			a.WorldCFrame = CFrame.fromMatrix(world, axis, f.Y)
		else
			a.WorldCFrame = CFrame.fromMatrix(world, f.X, f.Z)
		end
		return a
	end
	local blade = parts.Blade or handle
	attach(handle, "Origin", { 0, 0, 0 })
	local aCore = attach(handle, "Core", P.Core)
	local aRoot = attach(blade, "BladeRoot", P.BladeRoot)
	local aTip = attach(blade, "BladeTip", P.BladeTip)
	local bladeSpots = {}
	for i, p in ipairs(LAYOUT.bladeSpots) do
		bladeSpots[i] = attach(blade, "BladeFX" .. i, p)
	end

	-- the aura: energy and smoke spiralling up the shaft, and flares off the blade's back.
	-- Chains of curved camera-facing beams (each attachment's X axis follows the path, so the
	-- segments join smoothly); their textures scroll, so the energy keeps flowing.
	local auraOn = vfxConfig.Aura ~= false
	local flow = vfxConfig.AuraSpeed or 0.7
	local function auraChain(name, nodes, widthFn, props, parent)
		local atts = {}
		for i, p in ipairs(nodes) do
			local prev, nxt = nodes[math.max(1, i - 1)], nodes[math.min(#nodes, i + 1)]
			local tangent = toWorld(f, nxt) - toWorld(f, prev)
			atts[i] = make("Attachment", { Name = name .. i }, parent)
			local t = tangent.Unit
			local up = math.abs(t:Dot(f.Y)) > 0.95 and f.X or f.Y
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
	for i, path in ipairs(LAYOUT.spirals) do
		local wmax = LAYOUT.spiralWidths[i]
		local nodes = every(path, 4)
		auraChain("AuraSpiral" .. i, nodes, function(t)
			return 0.04 + wmax * 1.2 * math.sin(math.pi * t) ^ 0.8
		end, {
			Texture = tex("Ribbon"),
			TextureSpeed = flow,
			LightEmission = 1,
			Transparency = NumberSequence.new(0.1),
			ZOffset = 0.1,
			Attributes = { TextureKey = "Ribbon", Aura = true },
		}, handle)
		auraChain("AuraSmoke" .. i, nodes, function(t)
			return 0.06 + wmax * 1.8 * math.sin(math.pi * t) ^ 0.8
		end, {
			Texture = tex("SmokeRibbon"),
			TextureSpeed = flow * 0.6,
			LightEmission = 0,
			Transparency = NumberSequence.new(0.2),
			ZOffset = 0,
			Attributes = { TextureKey = "SmokeRibbon", Aura = true },
		}, handle)
	end
	for i, path in ipairs(LAYOUT.flares) do
		local wmax = LAYOUT.flareWidths[i]
		auraChain("AuraFlare" .. i, every(path, 3), function(t)
			return 0.02 + wmax * math.sin(math.pi * t) ^ 0.7
		end, {
			Texture = tex("Ribbon"),
			TextureSpeed = flow * 1.3,
			LightEmission = 1,
			Transparency = NumberSequence.new(0.15),
			ZOffset = 0.1,
			Attributes = { TextureKey = "Ribbon", Aura = true },
		}, blade)
	end

	local box = Enum.ParticleEmitterShape.Box
	local still = NumberRange.new(0)
	local function smokeProps(rate, size)
		return {
			Name = "AuraSmoke",
			Texture = tex("Smoke"),
			FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot,
			Rate = rate,
			Lifetime = NumberRange.new(1.0, 1.6),
			Speed = NumberRange.new(0.15, 0.5),
			SpreadAngle = Vector2.new(180, 180),
			Acceleration = Vector3.new(0, 0.6, 0),
			Drag = 1,
			Rotation = NumberRange.new(0, 360),
			RotSpeed = NumberRange.new(-30, 30),
			Size = ns({ { 0, size * 0.6 * s }, { 1, size * 1.3 * s } }),
			Transparency = ns({ { 0, 1 }, { 0.2, 0.35 }, { 1, 1 } }),
			LightEmission = 0,
			LightInfluence = 0,
			Attributes = { TextureKey = "Smoke", Flipbook = true },
		}
	end
	local function sparkProps(rate)
		return {
			Name = "AuraSparks",
			Texture = tex("Spark"),
			Rate = rate,
			Lifetime = NumberRange.new(0.8, 1.4),
			Speed = NumberRange.new(0.2, 0.6),
			SpreadAngle = Vector2.new(180, 180),
			Acceleration = Vector3.new(0, 0.8, 0),
			Size = ns({ { 0, 0 }, { 0.2, 0.07 * s }, { 1, 0 } }),
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = 0.3,
			Attributes = { TextureKey = "Spark" },
		}
	end
	local function shardProps(rate)
		return {
			Name = "AuraShards",
			Texture = tex("Shard"),
			Rate = rate,
			Lifetime = NumberRange.new(1.2, 2.0),
			Speed = NumberRange.new(0.1, 0.4),
			SpreadAngle = Vector2.new(180, 180),
			Rotation = NumberRange.new(-180, 180),
			RotSpeed = NumberRange.new(-90, 90),
			Size = ns({ { 0, 0 }, { 0.2, 0.16 * s }, { 0.8, 0.14 * s }, { 1, 0 } }),
			LightEmission = 0.8,
			LightInfluence = 0,
			ZOffset = 0.3,
			Attributes = { TextureKey = "Shard" },
		}
	end
	-- dark smoke, sparks and crystal fragments along the shaft
	local shaftSmoke = smokeProps(5, 0.9)
	shaftSmoke.Shape, shaftSmoke.ShapeStyle = box, Enum.ParticleEmitterShapeStyle.Volume
	make("ParticleEmitter", shaftSmoke, fxShaft)
	local shaftSparks = sparkProps(8)
	shaftSparks.Shape, shaftSparks.ShapeStyle = box, Enum.ParticleEmitterShapeStyle.Volume
	make("ParticleEmitter", shaftSparks, fxShaft)
	-- along the blade: smoke, sparks, floating shards and magical drips off the edge
	for _, a in ipairs(bladeSpots) do
		make("ParticleEmitter", smokeProps(1.2, 0.8), a)
		make("ParticleEmitter", sparkProps(2), a)
		make("ParticleEmitter", shardProps(0.5), a)
		make("ParticleEmitter", {
			Name = "Drips",
			Texture = tex("Drip"),
			Orientation = Enum.ParticleOrientation.VelocityParallel,
			EmissionDirection = Enum.NormalId.Bottom,
			Rate = 0.8,
			Lifetime = NumberRange.new(0.5, 0.8),
			Speed = NumberRange.new(0.2, 0.5),
			SpreadAngle = Vector2.new(10, 10),
			Acceleration = Vector3.new(0, -5, 0),
			Size = ns({ { 0, 0.1 * s }, { 1, 0.2 * s } }),
			Transparency = ns({ { 0, 0.1 }, { 0.8, 0.3 }, { 1, 1 } }),
			LightEmission = 1,
			LightInfluence = 0,
			Attributes = { TextureKey = "Drip" },
		}, a)
		make("ParticleEmitter", {
			Name = "SwingSparks",
			Texture = tex("Spark"),
			Orientation = Enum.ParticleOrientation.VelocityParallel,
			Rate = 0,
			Lifetime = NumberRange.new(0.25, 0.45),
			Speed = NumberRange.new(8, 16),
			SpreadAngle = Vector2.new(180, 180),
			Drag = 5,
			Acceleration = Vector3.new(0, -8, 0),
			Size = ns({ { 0, 0.2 * s }, { 1, 0 } }),
			Transparency = ns({ { 0, 0 }, { 1, 1 } }),
			LightEmission = 1,
			LightInfluence = 0,
			Attributes = { TextureKey = "Spark" },
		}, a)
		make("ParticleEmitter", {
			Name = "SwingShards",
			Texture = tex("Shard"),
			Rate = 0,
			Lifetime = NumberRange.new(0.5, 0.8),
			Speed = NumberRange.new(3, 7),
			SpreadAngle = Vector2.new(180, 180),
			Drag = 3,
			Acceleration = Vector3.new(0, -6, 0),
			Rotation = NumberRange.new(-180, 180),
			RotSpeed = NumberRange.new(-300, 300),
			Size = ns({ { 0, 0.22 * s }, { 1, 0.06 * s } }),
			LightEmission = 0.8,
			LightInfluence = 0,
			Attributes = { TextureKey = "Shard" },
		}, a)
	end
	-- the crystal core: the source of the energy, with its glow, light, smoke and fragments
	make("ParticleEmitter", {
		Name = "CoreGlow",
		Texture = tex("Glow"),
		Rate = 3,
		Lifetime = NumberRange.new(0.8),
		Speed = still,
		LockedToPart = true,
		Size = ns({ { 0, 1.0 * s }, { 0.5, 1.3 * s }, { 1, 1.0 * s } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.45 }, { 0.7, 0.45 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = -0.2,
		Attributes = { TextureKey = "Glow" },
	}, aCore)
	make("ParticleEmitter", smokeProps(2.5, 1.0), aCore)
	make("ParticleEmitter", shardProps(1.5), aCore)
	make("ParticleEmitter", sparkProps(4), aCore)
	make("PointLight", {
		Name = "CoreLight",
		Range = 12 * s,
		Brightness = 2,
		Shadows = false,
		Attributes = { ColorKey = "Light" },
	}, aCore)

	-- swing trails along the blade
	make("Trail", {
		Name = "SwingTrail",
		Attachment0 = aRoot,
		Attachment1 = aTip,
		Texture = tex("Trail"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.2,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 0.6,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Trail", SwingTrail = true },
	}, blade)
	make("Trail", {
		Name = "SwingGlow",
		Attachment0 = aRoot,
		Attachment1 = aTip,
		Texture = tex("Glow"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.28,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0.5 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Glow", SwingTrail = true },
	}, blade)

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
	local okVfx, VFX = pcall(require, folder:FindFirstChild("ScytheVFX"))
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
		note("Scythe not found, so only the scripts were updated (the existing scythe was kept)")
	else
		note("Scythe not found: import Scythe.fbx (or .glb) with the 3D Importer, then run this again")
	end
end

if recording then
	pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
end

print(("[CrimsonReaper] Install finished%s. Scythe: %s | Scripts: ReplicatedStorage.CrimsonScythe, "):format(
	#notes > 0 and (" with " .. #notes .. " note(s) above") or "",
	tool and tool:GetFullName() or "not built"
) .. "ServerScriptService.ScytheServer, StarterPlayerScripts.ScytheClient")
