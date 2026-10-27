-- Mo Feng Blade effects. Lives in ReplicatedStorage.MoFengSword.SwordVFX.
-- Clients play everything here; the server only calls ApplyTheme / ComputeImpact.

local Debris = game:GetService("Debris")
local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

local Folder = script.Parent
local Config = require(Folder:WaitForChild("Config"))

local SwordVFX = {}

-- ---------------------------------------------------------------- lookups

local function assets()
	return Folder:FindFirstChild("Assets")
end

-- Returns the texture id for a key, and true when it had to use a built-in fallback.
function SwordVFX.Texture(key)
	local override = Config.Textures[key]
	if override and override ~= "" then
		return override, false
	end
	local a = assets()
	local id = a and a:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id, false
	end
	return Config.FallbackTextures[key] or Config.FallbackTextures.Default, true
end

function SwordVFX.GetTheme(tool)
	local name = (tool and tool:GetAttribute("Theme")) or Config.DefaultTheme
	return Config.Themes[name] or Config.Themes[Config.DefaultTheme], name
end

-- Recolours everything tagged with a ColorRole attribute, refreshes textures
-- tagged with a TextureKey attribute, and swaps the hilt texture.
function SwordVFX.ApplyTheme(tool)
	local theme = SwordVFX.GetTheme(tool)
	for _, inst in ipairs(tool:GetDescendants()) do
		local key = inst:GetAttribute("TextureKey")
		if key and (inst:IsA("ParticleEmitter") or inst:IsA("Trail") or inst:IsA("Beam")) then
			local id, fallback = SwordVFX.Texture(key)
			inst.Texture = id
			if inst:IsA("ParticleEmitter") and inst:GetAttribute("Flipbook") then
				-- the built-in fallback isn't a 4x4 sheet, so only animate our own texture
				inst.FlipbookLayout = fallback and Enum.ParticleFlipbookLayout.None or Enum.ParticleFlipbookLayout.Grid4x4
			end
		end
		local role = inst:GetAttribute("ColorRole")
		if role then
			local c1 = theme[role] or theme.Primary
			local c2 = theme[inst:GetAttribute("ColorRole2") or role] or c1
			if inst:IsA("BasePart") or inst:IsA("Light") then
				inst.Color = c1
			elseif inst:IsA("ParticleEmitter") or inst:IsA("Trail") or inst:IsA("Beam") then
				inst.Color = ColorSequence.new(c1, c2)
			end
		end
	end
	local hilt = tool:FindFirstChild("Hilt")
	local a = assets()
	if hilt and hilt:IsA("MeshPart") and a then
		local id = a:GetAttribute(theme.Hilt == "Gold" and "Tex_HiltGold" or "Tex_HiltSilver")
		if typeof(id) == "string" and id ~= "" then
			hilt.TextureID = id
		end
	end
end

-- Where the special attack lands: on the ground a few studs in front of the player.
function SwordVFX.ComputeImpact(character)
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return Vector3.zero
	end
	local ahead = root.Position + root.CFrame.LookVector * (Config.Combat.SpecialRange * 0.55)
	local ignore = { character }
	local fx = Workspace:FindFirstChild("MoFengFX")
	if fx then
		table.insert(ignore, fx)
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore
	local hit = Workspace:Raycast(ahead + Vector3.new(0, 4, 0), Vector3.new(0, -14, 0), params)
	return hit and hit.Position or (ahead - Vector3.new(0, 2.8, 0))
end

-- ---------------------------------------------------------------- helpers

local function ns(points)
	local keys = {}
	for _, p in ipairs(points) do
		table.insert(keys, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(keys)
end

local function fxFolder()
	local f = Workspace:FindFirstChild("MoFengFX")
	if not f then
		f = Instance.new("Folder")
		f.Name = "MoFengFX"
		f.Parent = Workspace
	end
	return f
end

-- Runs step(t) every frame for `duration` seconds, t going 0 -> 1.
local function animate(duration, step)
	local start = os.clock()
	local conn
	conn = RunService.RenderStepped:Connect(function()
		local t = math.min(1, (os.clock() - start) / duration)
		local ok = pcall(step, t)
		if t >= 1 or not ok then
			conn:Disconnect()
		end
	end)
end

local function easeOut(t)
	return 1 - (1 - t) ^ 3
end

local function spawnAsset(name)
	local a = assets()
	local template = a and a:FindFirstChild(name)
	if not template then
		return nil
	end
	local part = template:Clone()
	part.Anchored = true
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.CastShadow = false
	part.Parent = fxFolder()
	return part, template.Size
end

-- Places a VFX mesh so its Blender axes line up with `frame` (X right, Y forward, Z normal).
local function placeInFrame(part, baseSize, frame, scale)
	local toLocal = part:GetAttribute("BlenderToLocal")
	if typeof(toLocal) ~= "CFrame" then
		toLocal = CFrame.identity
	end
	local pivot = part:GetAttribute("PivotOffset")
	if typeof(pivot) ~= "Vector3" then
		pivot = Vector3.zero
	end
	part.Size = baseSize * scale
	part.CFrame = frame * CFrame.new(-pivot * scale) * toLocal:Inverse()
end

local function emit(tool, name, count)
	for _, d in ipairs(tool:GetDescendants()) do
		if d.Name == name and d:IsA("ParticleEmitter") then
			d:Emit(count)
		end
	end
end

local function playSound(tool, name)
	local handle = tool:FindFirstChild("Handle")
	local sound = handle and handle:FindFirstChild(name)
	if sound and sound:IsA("Sound") and sound.SoundId ~= "" then
		sound:Play()
	end
end

local trailTokens = setmetatable({}, { __mode = "k" })

local function flashTrails(tool, duration)
	for _, d in ipairs(tool:GetDescendants()) do
		if d:IsA("Trail") then
			local token = (trailTokens[d] or 0) + 1
			trailTokens[d] = token
			d.Enabled = true
			task.delay(duration, function()
				if trailTokens[d] == token and d.Parent then
					d.Enabled = false
				end
			end)
		end
	end
end

local function pulseLight(tool, brightness, duration)
	local edge = tool:FindFirstChild("BladeEdge")
	local light = edge and edge:FindFirstChild("BladeLight")
	if not light then
		return
	end
	local base = light:GetAttribute("BaseBrightness") or light.Brightness
	light:SetAttribute("BaseBrightness", base)
	light.Brightness = brightness
	TweenService:Create(light, TweenInfo.new(duration, Enum.EasingStyle.Quad), { Brightness = base }):Play()
end

local function boostRates(tool, factor, duration)
	for _, d in ipairs(tool:GetDescendants()) do
		if d:IsA("ParticleEmitter") and (d:GetAttribute("BaseRate") or d.Rate) > 0 then
			local base = d:GetAttribute("BaseRate") or d.Rate
			d:SetAttribute("BaseRate", base)
			d.Rate = base * factor
			task.delay(duration, function()
				if d.Parent then
					d.Rate = base
				end
			end)
		end
	end
end

-- ---------------------------------------------------------------- building blocks

-- A crescent slash in front of the character. roll: degrees around the forward axis.
local function slash(character, theme, roll, radius, duration, travel)
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	local arc, arcSize = spawnAsset("SlashArc")
	local core, coreSize = spawnAsset("SlashCore")
	if arc then
		arc.Material = Enum.Material.ForceField
		arc.Color = theme.Primary
	end
	if core then
		core.Material = Enum.Material.Neon
		core.Color = theme.Core
	end
	local rcf = root.CFrame
	local base = CFrame.fromMatrix(rcf.Position + Vector3.new(0, 0.7, 0), rcf.RightVector, rcf.LookVector)
		* CFrame.Angles(0, math.rad(roll), 0)
	animate(duration, function(t)
		local e = easeOut(t)
		-- sweep the crescent around its centre so the thick head leads the swing
		local frame = base * CFrame.new(0, (travel or 0) * e, 0) * CFrame.Angles(0, 0, math.rad(35 - 50 * e))
		local s = radius * (0.78 + 0.32 * e)
		if arc then
			placeInFrame(arc, arcSize, frame, s)
			arc.Transparency = 0.05 + 0.95 * t ^ 1.6
		end
		if core then
			placeInFrame(core, coreSize, frame, s * 1.005)
			core.Transparency = math.min(1, t * 1.7)
		end
	end)
	if arc then
		Debris:AddItem(arc, duration + 0.1)
	end
	if core then
		Debris:AddItem(core, duration + 0.1)
	end
end

local function shards(origin, theme, count, speed, life)
	for i = 1, count do
		local part, size = spawnAsset(i % 2 == 0 and "Shard2" or "Shard1")
		if not part then
			return
		end
		part.Material = Enum.Material.Neon
		part.Color = theme.Core
		local dir = Vector3.new(math.random() - 0.5, math.random() * 0.8 - 0.1, math.random() - 0.5)
		dir = dir.Magnitude > 1e-3 and dir.Unit or Vector3.yAxis
		local spin = Vector3.new(math.random(), math.random(), math.random()) * 12
		part.Size = size * (0.8 + math.random() * 0.8)
		animate(life, function(t)
			local pos = origin + dir * speed * life * (1 - (1 - t) ^ 2) - Vector3.new(0, 4 * t * t, 0)
			part.CFrame = CFrame.new(pos) * CFrame.Angles(spin.X * t, spin.Y * t, spin.Z * t)
			part.Transparency = t * t
		end)
		Debris:AddItem(part, life + 0.1)
	end
end

local function newEmitter(parent, props)
	local e = Instance.new("ParticleEmitter")
	e.Enabled = false
	e.LightEmission = 1
	e.LightInfluence = 0
	for k, v in pairs(props) do
		e[k] = v
	end
	e.Parent = parent
	return e
end

-- Sparks, flash, embers and a light at a world position.
local function burstAt(position, theme, opts)
	local att = Instance.new("Attachment")
	att.Parent = Workspace.Terrain
	att.WorldPosition = position
	newEmitter(att, {
		Texture = SwordVFX.Texture("Spark"),
		Orientation = Enum.ParticleOrientation.VelocityParallel,
		Lifetime = NumberRange.new(0.25, 0.5),
		Speed = NumberRange.new(14, 26),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 4,
		Acceleration = Vector3.new(0, -12, 0),
		Size = ns({ { 0, 0.28 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		Color = ColorSequence.new(theme.Core, theme.Primary),
	}):Emit(opts.sparks)
	newEmitter(att, {
		Texture = SwordVFX.Texture("Flash"),
		Lifetime = NumberRange.new(0.12, 0.16),
		Speed = NumberRange.new(0),
		Rotation = NumberRange.new(0, 360),
		Size = ns({ { 0, opts.flash * 0.4 }, { 0.3, opts.flash }, { 1, opts.flash * 1.1 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		Color = ColorSequence.new(theme.Core),
		ZOffset = 1,
	}):Emit(1)
	newEmitter(att, {
		Texture = SwordVFX.Texture("Ember"),
		Lifetime = NumberRange.new(0.5, 1.0),
		Speed = NumberRange.new(3, 9),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 2,
		Acceleration = Vector3.new(0, 3, 0),
		Size = ns({ { 0, 0.14 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 0.7, 0.2 }, { 1, 1 } }),
		Color = ColorSequence.new(theme.Vein, theme.Primary),
	}):Emit(opts.embers)
	local light = Instance.new("PointLight")
	light.Color = theme.Primary
	light.Range = opts.lightRange
	light.Brightness = opts.light
	light.Shadows = false
	light.Parent = att
	TweenService:Create(light, TweenInfo.new(0.4, Enum.EasingStyle.Quad), { Brightness = 0 }):Play()
	if Config.Sounds.Impact ~= "" then
		local s = Instance.new("Sound")
		s.SoundId = Config.Sounds.Impact
		s.Volume = 0.7
		s.Parent = att
		s:Play()
	end
	Debris:AddItem(att, 1.5)
end

-- Expanding ring. `frame` gives the ring plane (its Blender Z is the ring's normal).
local function ring(frame, theme, radius, duration, thick)
	local wave, waveSize = spawnAsset("ShockRing")
	local core, coreSize = spawnAsset("RingCore")
	if wave then
		wave.Material = Enum.Material.ForceField
		wave.Color = theme.Primary
	end
	if core then
		core.Material = Enum.Material.Neon
		core.Color = theme.Core
	end
	animate(duration, function(t)
		local s = math.max(0.05, radius * easeOut(t))
		if wave then
			placeInFrame(wave, waveSize, frame * CFrame.Angles(0, 0, t * 0.6), s)
			wave.Transparency = t ^ 1.5
		end
		if core then
			placeInFrame(core, coreSize, frame, s)
			core.Transparency = math.min(1, (thick and 0.1 or 0.35) + t * 1.2)
		end
	end)
	if wave then
		Debris:AddItem(wave, duration + 0.1)
	end
	if core then
		Debris:AddItem(core, duration + 0.1)
	end
end

local function groundFrame(position)
	return CFrame.fromMatrix(position + Vector3.new(0, 0.15, 0), Vector3.xAxis, -Vector3.zAxis)
end

local function cameraFrame(position)
	local cam = Workspace.CurrentCamera
	if not cam then
		return groundFrame(position)
	end
	local look = CFrame.lookAt(position, cam.CFrame.Position)
	return CFrame.fromMatrix(position, look.RightVector, look.UpVector)
end

local function screenFlash(theme)
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "MoFengFlash"
	cc.Brightness = 0.28
	cc.Contrast = 0.15
	cc.Saturation = 0.15
	cc.TintColor = Color3.new(1, 1, 1):Lerp(theme.Core, 0.6)
	cc.Parent = Lighting
	TweenService:Create(cc, TweenInfo.new(0.35, Enum.EasingStyle.Quad), {
		Brightness = 0,
		Contrast = 0,
		Saturation = 0,
		TintColor = Color3.new(1, 1, 1),
	}):Play()
	Debris:AddItem(cc, 0.4)
end

local shakeCount = 0

local function cameraShake(intensity, duration)
	shakeCount += 1
	local name = "MoFengShake" .. shakeCount
	local start = os.clock()
	RunService:BindToRenderStep(name, Enum.RenderPriority.Camera.Value + 1, function()
		local t = (os.clock() - start) / duration
		local cam = Workspace.CurrentCamera
		if t >= 1 or not cam then
			RunService:UnbindFromRenderStep(name)
			return
		end
		local a = intensity * (1 - t) ^ 2
		cam.CFrame = cam.CFrame
			* CFrame.Angles(math.rad((math.random() - 0.5) * a), math.rad((math.random() - 0.5) * a), 0)
	end)
end

-- ---------------------------------------------------------------- attacks

function SwordVFX.Swing(tool, combo)
	local character = tool.Parent
	if not (character and character:IsA("Model")) then
		return
	end
	local theme = SwordVFX.GetTheme(tool)
	flashTrails(tool, 0.3)
	emit(tool, "SwingSparks", 16)
	emit(tool, "Fragments", 6)
	playSound(tool, "SwingSound")
	pulseLight(tool, 3, 0.25)
	local roll = Config.SlashAngles[combo] or 70
	local radius = Config.VFX.SlashRadius * (combo == 3 and 1.15 or 1)
	task.delay(0.05, function()
		slash(character, theme, roll, radius, 0.24, 0.6)
	end)
	local edge = tool:FindFirstChild("BladeEdge")
	local tip = edge and edge:FindFirstChild("BladeTip")
	if tip then
		task.delay(0.1, function()
			shards(tip.WorldPosition, theme, 3, 9, 0.35)
		end)
	end
end

function SwordVFX.SpecialCharge(tool)
	local windup = Config.Combat.SpecialWindup
	boostRates(tool, 3, windup + 0.3)
	pulseLight(tool, 6, windup + 0.4)
	flashTrails(tool, windup + 0.45)
	emit(tool, "Crackle", 25)
	emit(tool, "TipGlint", 2)
end

function SwordVFX.SpecialRelease(tool, impact, isLocalAttacker)
	local character = tool.Parent
	if not (character and character:IsA("Model")) then
		return
	end
	local theme = SwordVFX.GetTheme(tool)
	impact = impact or SwordVFX.ComputeImpact(character)
	local radius = Config.VFX.SpecialSlashRadius
	slash(character, theme, 90, radius, 0.4, 6)
	task.delay(0.06, function()
		slash(character, theme, 65, radius * 0.8, 0.35, 4)
	end)
	emit(tool, "SwingSparks", 30)
	emit(tool, "Fragments", 14)
	playSound(tool, "SpecialSound")
	task.delay(0.12, function()
		local frame = groundFrame(impact)
		ring(frame, theme, Config.VFX.ShockwaveRadius, 0.55, true)
		task.delay(0.07, function()
			ring(frame, theme, Config.VFX.ShockwaveRadius * 0.6, 0.4, false)
		end)
		burstAt(impact + Vector3.new(0, 0.5, 0), theme, { sparks = 60, flash = 9, embers = 30, light = 8, lightRange = 24 })
		shards(impact + Vector3.new(0, 1, 0), theme, 10, 18, 0.6)
		local cam = Workspace.CurrentCamera
		if Config.VFX.ScreenFlash and cam and (cam.CFrame.Position - impact).Magnitude < 70 then
			screenFlash(theme)
		end
		if isLocalAttacker and Config.VFX.CameraShake then
			cameraShake(2.2, 0.35)
		end
	end)
end

function SwordVFX.Impact(position, themeName, isSpecial)
	local theme = Config.Themes[themeName] or Config.Themes[Config.DefaultTheme]
	burstAt(position, theme, {
		sparks = isSpecial and 30 or 16,
		flash = isSpecial and 4 or 2.2,
		embers = 8,
		light = 4,
		lightRange = 10,
	})
	ring(cameraFrame(position), theme, isSpecial and 4 or 2.2, 0.22, false)
end

-- ---------------------------------------------------------------- idle extras

local idleStates = {}

local function bolt(tool, edge, base, tip)
	local theme = SwordVFX.GetTheme(tool)
	local half = (tool:GetAttribute("BladeHalfWidth") or 0.28) * 1.1
	local across = base.CFrame.RightVector
	local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
	local h0 = math.random()
	local h1 = math.clamp(h0 + (math.random() - 0.5) * 0.35, 0, 1)
	a0.Position = base.Position:Lerp(tip.Position, h0) + across * half * (math.random() < 0.5 and -1 or 1)
	a1.Position = base.Position:Lerp(tip.Position, h1) + across * half * (math.random() < 0.5 and -1 or 1)
	a0.Parent = edge
	a1.Parent = edge
	local beam = Instance.new("Beam")
	beam.Attachment0 = a0
	beam.Attachment1 = a1
	beam.Texture = SwordVFX.Texture("Lightning")
	beam.TextureMode = Enum.TextureMode.Stretch
	beam.TextureSpeed = 4
	beam.Width0 = 0.12
	beam.Width1 = 0.08
	beam.CurveSize0 = (math.random() - 0.5) * 1.2
	beam.CurveSize1 = (math.random() - 0.5) * 1.2
	beam.Segments = 12
	beam.FaceCamera = true
	beam.LightEmission = 1
	beam.LightInfluence = 0
	beam.Color = ColorSequence.new(theme.Core, theme.Vein)
	beam.Parent = edge
	task.delay(0.06, function()
		beam.Transparency = NumberSequence.new(0.45)
	end)
	for _, inst in ipairs({ beam, a0, a1 }) do
		Debris:AddItem(inst, 0.14)
	end
end

function SwordVFX.StartIdle(tool)
	if idleStates[tool] then
		return
	end
	local edge = tool:FindFirstChild("BladeEdge")
	local base = edge and edge:FindFirstChild("BladeBase")
	local tip = edge and edge:FindFirstChild("BladeTip")
	if not (base and tip) then
		return
	end
	local scale = tool:GetAttribute("SwordScale") or 1
	local state = { rocks = {}, nextBolt = os.clock() + 0.5, nextBurst = os.clock() + 1.5 }
	for i = 1, Config.VFX.OrbitRocks do
		local rock, size = spawnAsset("Rock" .. ((i - 1) % 3 + 1))
		if rock then
			rock.Size = size * scale * (0.8 + 0.4 * math.random())
			table.insert(state.rocks, {
				part = rock,
				phase = math.random() * math.pi * 2,
				speed = 0.8 + math.random() * 0.6,
				height = 0.25 + 0.6 * (i - 0.5) / Config.VFX.OrbitRocks,
				radius = (0.42 + math.random() * 0.15) * scale,
			})
		end
	end
	state.conn = RunService.RenderStepped:Connect(function()
		if not (tool.Parent and edge.Parent) then
			SwordVFX.StopIdle(tool)
			return
		end
		local now = os.clock()
		local p0, p1 = base.WorldPosition, tip.WorldPosition
		local cam = Workspace.CurrentCamera
		local near = cam ~= nil and (cam.CFrame.Position - p0).Magnitude < Config.VFX.IdleRange
		local axis = p1 - p0
		local len = axis.Magnitude
		if len < 1e-3 then
			return
		end
		axis /= len
		local width = base.WorldCFrame.RightVector
		local normal = width:Cross(axis)
		for _, r in ipairs(state.rocks) do
			if near then
				local a = now * r.speed + r.phase
				local pos = p0
					+ axis * (len * r.height + 0.06 * math.sin(now * 2 + r.phase))
					+ (width * math.cos(a) + normal * math.sin(a)) * r.radius
				r.part.CFrame = CFrame.new(pos) * CFrame.Angles(now * 0.9 + r.phase, now * 0.6, now * 0.4)
				r.part.Transparency = 0
			else
				r.part.Transparency = 1
			end
		end
		if not near then
			return
		end
		if Config.VFX.Lightning and now >= state.nextBolt then
			state.nextBolt = now + 0.6 + math.random() * 1.2
			bolt(tool, edge, base, tip)
		end
		if now >= state.nextBurst then
			state.nextBurst = now + 2.2 + math.random() * 2
			emit(tool, "Crackle", 8)
			emit(tool, "TipGlint", 1)
			pulseLight(tool, 2.6, 0.4)
		end
	end)
	idleStates[tool] = state
end

function SwordVFX.StopIdle(tool)
	local state = idleStates[tool]
	if not state then
		return
	end
	idleStates[tool] = nil
	if state.conn then
		state.conn:Disconnect()
	end
	for _, r in ipairs(state.rocks) do
		r.part:Destroy()
	end
end

return SwordVFX
