-- ======================================================================
-- Installer body (SOURCES and LAYOUT are defined above by build_installer.py)
-- ======================================================================

local ChangeHistoryService = game:GetService("ChangeHistoryService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Selection = game:GetService("Selection")
local ServerScriptService = game:GetService("ServerScriptService")
local StarterPlayer = game:GetService("StarterPlayer")
local Workspace = game:GetService("Workspace")

local NAME = "GoldenKingBalloon"
local PARTS = {
	"Balloon",
	"BalloonNozzle",
	"String",
	"Crown",
	"CrownGems",
	"LeftWing",
	"RightWing",
	"LeftWingFeathers",
	"RightWingFeathers",
}
-- what each part is made of (BalloonCosmetic styles them by this)
local KIND = {
	Balloon = "Balloon",
	BalloonNozzle = "Gold",
	String = "String",
	Crown = "Gold",
	CrownGems = "Gem",
	LeftWing = "Feather",
	RightWing = "Feather",
	LeftWingFeathers = "Feather",
	RightWingFeathers = "Feather",
}

local notes = {}
local function note(msg)
	table.insert(notes, msg)
	warn("[GoldenKingBalloon] " .. msg)
end

local recording
pcall(function()
	recording = ChangeHistoryService:TryBeginRecording("Install Golden King Balloon")
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

-- Exact name first, then e.g. "LeftWing.001" (but never "LeftWingFeathers" for "LeftWing").
local function findPart(root, name)
	local exact = root:FindFirstChild(name, true)
	if exact and exact:IsA("BasePart") then
		return exact
	end
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("BasePart") and d.Name:sub(1, #name) == name and not d.Name:sub(#name + 1, #name + 1):match("%a") then
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

local folder = upsert(ReplicatedStorage, "Folder", NAME)
local configModule = upsertScript(folder, "ModuleScript", "Config", SOURCES.Config, true)
upsertScript(folder, "ModuleScript", "Layout", SOURCES.Layout, false)
local cosmeticModule = upsertScript(folder, "ModuleScript", "BalloonCosmetic", SOURCES.BalloonCosmetic, false)
local assetsFolder = upsert(folder, "Folder", "Assets")
upsertScript(ServerScriptService, "Script", "GoldenBalloonServer", SOURCES.Server, false)
local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
	or make("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, StarterPlayer)
upsertScript(playerScripts, "LocalScript", "GoldenBalloonClient", SOURCES.Client, false)

local okConfig, Config = pcall(require, configModule)
if not okConfig then
	note("Config has an error, using defaults for the install: " .. tostring(Config))
	Config = { Colors = {}, FallbackTextures = {}, VFX = {} }
end

-- ---------------------------------------------------------------- effect textures

local vfxImport = findImport("GoldenBalloonVFX")
if vfxImport then
	for key in pairs(assetsFolder:GetAttributes()) do
		assetsFolder:SetAttribute(key, nil)
	end
	local found = 0
	for _, key in ipairs(LAYOUT.textureKeys) do
		local carrier = findPart(vfxImport, "Tex_" .. key)
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
	vfxImport:Destroy()
else
	note("GoldenBalloonVFX not found: import GoldenBalloonVFX.fbx (or .glb) to bring in the effect textures, then run this again")
end

local function tex(key)
	local id = assetsFolder:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds"
end

-- ---------------------------------------------------------------- the balloon

local import = findImport(NAME)
local template

if import then
	local f = markerFrame(import)
	local parts = {}
	for _, name in ipairs(PARTS) do
		parts[name] = findPart(import, name)
		if not parts[name] then
			note("balloon part missing: " .. name)
		end
	end
	assert(parts.Balloon, NAME .. " is missing its Balloon mesh")

	-- 1 Blender unit = BALLOON_SCALE studs, whatever units the importer used
	local factor = LAYOUT.balloonScale / f.k
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
		f = markerFrame(import)
	end
	-- the importer keeps handedness, but check it with the left wing (it sits on Blender's -X side)
	if parts.LeftWing and (parts.LeftWing.Position - f.O):Dot(f.X) > 0 then
		f.X = -f.X
		note("the import came in mirrored left to right; corrected")
	end
	local s = LAYOUT.balloonScale
	local P = LAYOUT.points

	local function dir(v)
		return (f.X * v[1] + f.Y * v[2] + f.Z * v[3]).Unit
	end
	-- the balloon's own frame: upright, looking out of its front (the crown's big gem)
	local function frameAt(point)
		return CFrame.fromMatrix(toWorld(f, point), -f.X, f.Z)
	end
	local pivot = frameAt(P.Pivot)

	for name, p in pairs(parts) do
		local kind = KIND[name]
		p.Anchored = false
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.Massless = true
		p:SetAttribute("Kind", kind)
		if kind == "Gold" then
			p.Material = Enum.Material.Metal
		elseif kind == "Gem" then
			p:SetAttribute("GemTexture", textureOf(p))
			clearSurfaceAppearance(p)
		elseif kind == "Feather" then
			p:SetAttribute("FeatherTexture", textureOf(p))
			clearSurfaceAppearance(p)
		elseif kind == "String" then
			clearSurfaceAppearance(p)
			p.Material = Enum.Material.SmoothPlastic
			p.TextureID = ""
		end
	end

	-- GoldenKingBalloon
	-- ├── Balloon, BalloonNozzle, String, Crown, CrownGems, LeftWing, RightWing
	-- ├── WingFeathers (LeftWingFeathers, RightWingFeathers)
	-- └── VFX (GoldenAura, GoldenParticles, Sparkles, EnergyTrails)
	template = make("Model", { Name = NAME, Attributes = { BalloonScale = s } }, nil)
	local wingFeathers = make("Model", { Name = "WingFeathers" }, template)
	local vfx = make("Model", { Name = "VFX" }, template)
	for name, p in pairs(parts) do
		p.Parent = name:find("Feathers") and wingFeathers or template
	end
	local balloon = parts.Balloon
	template.PrimaryPart = balloon
	balloon.PivotOffset = balloon.CFrame:ToObjectSpace(pivot)

	local function weldTo(p0, p1)
		make("WeldConstraint", { Name = "Weld", Part0 = p0, Part1 = p1 }, p1)
	end
	local function jointAt(name, p0, p1, cf)
		return make("Weld", { Name = name, Part0 = p0, Part1 = p1, C0 = p0.CFrame:ToObjectSpace(cf), C1 = p1.CFrame:ToObjectSpace(cf) }, p1)
	end
	for _, name in ipairs({ "BalloonNozzle", "String", "Crown", "CrownGems" }) do
		if parts[name] then
			weldTo(balloon, parts[name])
		end
	end
	-- each wing turns on a hinge at its root (the client flaps it a little); its layered
	-- feathers are welded to it
	for _, side in ipairs({ "Left", "Right" }) do
		local wing, feathers = parts[side .. "Wing"], parts[side .. "WingFeathers"]
		local w = LAYOUT.wings[side]
		if wing then
			jointAt("WingHinge", balloon, wing, CFrame.fromMatrix(toWorld(f, w.pos), dir(w.out), f.Z))
			if feathers then
				weldTo(wing, feathers)
			end
		elseif feathers then
			weldTo(balloon, feathers)
		end
	end

	local function attach(part, name, point)
		local a = make("Attachment", { Name = name }, part)
		a.WorldCFrame = frameAt(point)
		return a
	end
	attach(balloon, "Pivot", P.Pivot)
	attach(balloon, "Nozzle", P.Nozzle)
	attach(balloon, "StringEnd", P.StringEnd)
	attach(balloon, "CrownTop", P.CrownTop)
	local aGem = attach(balloon, "CrownGem", P.CrownGem)

	-- ------------------------------------------------------------ the golden aura

	local function fxPart(name, size, point)
		local p = make("Part", {
			Name = name,
			Transparency = 1,
			Size = size * s,
			CFrame = frameAt(point),
			Anchored = false,
			CanCollide = false,
			CanQuery = false,
			CanTouch = false,
			Massless = true,
			CastShadow = false,
		}, vfx)
		return p
	end
	local auraPart = fxPart("GoldenAura", Vector3.new(1, 1, 1), P.Pivot)
	local particlesPart = fxPart("GoldenParticles", Vector3.new(4.4, 3.6, 1.8), { 0, 0, 0.2 })
	local sparklesPart = fxPart("Sparkles", Vector3.new(4.9, 4.4, 2.2), { 0, 0, 0.1 })
	local trailsPart = fxPart("EnergyTrails", Vector3.new(1, 1, 1), P.TrailCentre)
	weldTo(balloon, auraPart)
	weldTo(balloon, particlesPart)
	weldTo(balloon, sparklesPart)
	-- the trails turn slowly round the balloon (the client spins this weld)
	jointAt("TrailSpin", balloon, trailsPart, frameAt(P.TrailCentre))

	local box = Enum.ParticleEmitterShape.Box
	local volume = Enum.ParticleEmitterShapeStyle.Volume
	local still = NumberRange.new(0)

	-- golden aura: a soft yellow-white glow, a bigger gold glow behind it, small light rays,
	-- a glow behind each wing and a warm light
	local function glow(name, key, size, transparency, z, parent)
		return make("ParticleEmitter", {
			Name = name,
			Texture = tex(key),
			Rate = 2,
			Lifetime = NumberRange.new(1.0),
			Speed = still,
			LockedToPart = true,
			Size = ns({ { 0, size * 0.94 * s }, { 0.5, size * s }, { 1, size * 0.94 * s } }),
			Transparency = ns({ { 0, 1 }, { 0.3, transparency }, { 0.7, transparency }, { 1, 1 } }),
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = z,
			Attributes = { TextureKey = key, Group = "Aura" },
		}, parent)
	end
	glow("GoldenAura", "GlowSoft", 2.7, 0.62, -1.0, auraPart)
	glow("GoldenGlow", "GlowGold", 4.2, 0.8, -1.5, auraPart)
	local rays = glow("LightRays", "Rays", 3.4, 0.72, -2.0, auraPart)
	rays.Rotation = NumberRange.new(0, 360)
	rays.RotSpeed = NumberRange.new(-10, 10)
	for _, side in ipairs({ "Left", "Right" }) do
		local a = attach(auraPart, side .. "WingGlow", LAYOUT.wings[side].glow)
		glow("WingGlow", "GlowGold", 2.4, 0.82, -1.0, a)
	end
	make("PointLight", {
		Name = "BalloonLight",
		Range = 10 * s,
		Brightness = 1.2,
		Shadows = false,
		Color = Config.Colors.Light or Color3.fromRGB(255, 214, 120),
		Attributes = { ColorKey = "Light" },
	}, auraPart)
	-- a glint now and then on the crown's big gem
	make("ParticleEmitter", {
		Name = "CrownGlint",
		Texture = tex("Sparkle"),
		Rate = 0.8,
		Lifetime = NumberRange.new(0.35, 0.5),
		Speed = still,
		LockedToPart = true,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0 }, { 0.4, 0.4 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.3,
		Attributes = { TextureKey = "Sparkle", Group = "Aura" },
	}, aGem)

	-- golden particles: tiny motes drifting up round it, and golden feathers floating off it
	make("ParticleEmitter", {
		Name = "GoldenParticles",
		Texture = tex("Mote"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 10,
		Lifetime = NumberRange.new(1.4, 2.4),
		Speed = NumberRange.new(0.15, 0.4),
		SpreadAngle = Vector2.new(180, 180),
		Acceleration = Vector3.new(0, 0.35, 0),
		Size = ns({ { 0, 0 }, { 0.2, 0.09 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.3,
		Attributes = { TextureKey = "Mote", Group = "Aura" },
	}, particlesPart)
	make("ParticleEmitter", {
		Name = "FloatingFeathers",
		Texture = tex("Feather"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 0.6,
		Lifetime = NumberRange.new(3, 4.5),
		Speed = NumberRange.new(0.2, 0.5),
		SpreadAngle = Vector2.new(180, 180),
		Acceleration = Vector3.new(0, -0.3, 0),
		Drag = 0.5,
		Rotation = NumberRange.new(0, 360),
		RotSpeed = NumberRange.new(-40, 40),
		Size = NumberSequence.new(0.34 * s),
		Transparency = ns({ { 0, 1 }, { 0.15, 0.1 }, { 0.75, 0.1 }, { 1, 1 } }),
		LightEmission = 0.6,
		LightInfluence = 0.2,
		Attributes = { TextureKey = "Feather", Group = "Feathers" },
	}, particlesPart)

	-- sparkles and tiny glowing stars
	make("ParticleEmitter", {
		Name = "Sparkles",
		Texture = tex("Sparkle"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 3,
		Lifetime = NumberRange.new(0.45, 0.8),
		Speed = still,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0 }, { 0.4, 0.32 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.5,
		Attributes = { TextureKey = "Sparkle", Group = "Aura" },
	}, sparklesPart)
	make("ParticleEmitter", {
		Name = "Stars",
		Texture = tex("Star"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 6,
		Lifetime = NumberRange.new(0.6, 1.2),
		Speed = NumberRange.new(0, 0.15),
		SpreadAngle = Vector2.new(180, 180),
		Size = ns({ { 0, 0 }, { 0.5, 0.11 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.4,
		Attributes = { TextureKey = "Star", Group = "Aura" },
	}, sparklesPart)

	-- energy trails: thin swirling strands of gold light round the balloon (chains of curved,
	-- camera-facing beams whose texture flows), with soft wide swooshes under the first two
	attach(trailsPart, "Origin", P.Pivot).WorldCFrame = CFrame.fromMatrix(toWorld(f, P.Pivot), f.X, f.Y)
	local function chain(name, nodes, widthFn, props)
		local atts = {}
		for i, p in ipairs(nodes) do
			local prev, nxt = nodes[math.max(1, i - 1)], nodes[math.min(#nodes, i + 1)]
			local t = (toWorld(f, nxt) - toWorld(f, prev)).Unit
			local up = math.abs(t:Dot(f.Z)) > 0.95 and f.X or f.Z
			atts[i] = make("Attachment", { Name = name .. i }, trailsPart)
			atts[i].WorldCFrame = CFrame.fromMatrix(toWorld(f, p), t, (up - t * up:Dot(t)).Unit)
		end
		for i = 1, #atts - 1 do
			local a0, a1 = atts[i], atts[i + 1]
			local handle = (a1.WorldPosition - a0.WorldPosition).Magnitude / 3
			local beamProps = {
				Name = name,
				Attachment0 = a0,
				Attachment1 = a1,
				TextureMode = Enum.TextureMode.Wrap,
				CurveSize0 = handle,
				CurveSize1 = handle,
				Segments = 8,
				FaceCamera = true,
				LightEmission = 1,
				LightInfluence = 0,
				Width0 = widthFn((i - 1) / (#atts - 1)) * s,
				Width1 = widthFn(i / (#atts - 1)) * s,
			}
			for k, v in pairs(props) do
				beamProps[k] = v
			end
			make("Beam", beamProps, trailsPart)
		end
	end
	local flow = (Config.VFX or {}).TrailFlow or 0.5
	for i, path in ipairs(LAYOUT.trails) do
		local wmax = LAYOUT.trailWidths[i]
		chain("EnergyTrail" .. i, path, function(t)
			return 0.01 + wmax * 1.6 * math.sin(math.pi * t) ^ 0.7
		end, {
			Texture = tex("Trail"),
			TextureLength = 1.6 * s,
			TextureSpeed = -flow,
			Transparency = ns({ { 0, 0.1 }, { 1, 0.1 } }),
			ZOffset = 0.1,
			Attributes = { TextureKey = "Trail", Group = "Trails", FlowSign = -1 },
		})
		if i <= 2 then
			chain("EnergySwoosh" .. i, path, function(t)
				return 0.01 + wmax * 3.2 * math.sin(math.pi * t) ^ 1.2
			end, {
				Texture = tex("Swirl"),
				TextureLength = 2.4 * s,
				TextureSpeed = -flow * 0.6,
				Transparency = ns({ { 0, 0.55 }, { 1, 0.55 } }),
				ZOffset = 0,
				Attributes = { TextureKey = "Swirl", Group = "Trails", FlowSign = -0.6 },
			})
		end
	end

	for _, m in ipairs(f.markers) do
		m:Destroy()
	end
	import:Destroy()

	-- the template lives in ReplicatedStorage (the server clones it onto players, and your shop
	-- can clone it into a ViewportFrame); a preview copy goes in the workspace to look at
	local old = folder:FindFirstChild(NAME)
	if old then
		old:Destroy()
	end
	balloon.Anchored = true
	template.Parent = folder
	local oldPreview = Workspace:FindFirstChild(NAME .. "_Preview")
	if oldPreview then
		oldPreview:Destroy()
	end
	local preview = template:Clone()
	preview.Name = NAME .. "_Preview"
	preview.Parent = Workspace
	local okCosmetic, Cosmetic = pcall(require, cosmeticModule)
	if okCosmetic then
		Cosmetic.ApplyStyle(template)
		Cosmetic.ApplyStyle(preview)
	else
		note("could not preview the styles in Studio (" .. tostring(Cosmetic) .. "); they apply in game")
	end
	Selection:Set({ preview })
else
	template = folder:FindFirstChild(NAME)
	if template then
		note(NAME .. " import not found, so only the scripts were updated (the existing balloon was kept)")
	else
		note(NAME .. " not found: import GoldenKingBalloon.fbx (or .glb) with the 3D Importer, then run this again")
	end
end

if recording then
	pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
end

print(("[GoldenKingBalloon] Install finished%s. Balloon: %s | Scripts: ReplicatedStorage.GoldenKingBalloon, "):format(
	#notes > 0 and (" with " .. #notes .. " note(s) above") or "",
	template and template:GetFullName() or "not built"
) .. "ServerScriptService.GoldenBalloonServer, StarterPlayerScripts.GoldenBalloonClient")
