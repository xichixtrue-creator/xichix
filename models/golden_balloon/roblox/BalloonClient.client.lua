-- Golden King Balloon (client). Lives in StarterPlayerScripts.GoldenBalloonClient.
-- Animates every worn balloon on this screen: it floats beside its player with a gentle bob
-- and sway, follows them on a soft spring (leaning a little when they run), always stays
-- upright and faces the way they face (it never spins). The wings rise and fall slightly, the
-- golden energy trails turn round the balloon with bright streaks racing along them, and the
-- glow breathes. When its player dies, the balloon drifts up and away.

local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Folder = ReplicatedStorage:WaitForChild("GoldenKingBalloon")
local Config = require(Folder:WaitForChild("Config"))
local Layout = require(Folder:WaitForChild("Layout"))
local Balloon = require(Folder:WaitForChild("BalloonCosmetic"))

local TAU = 2 * math.pi

-- Config value with a default, so a Config kept from an older install still works.
local function opt(group, key, default)
	local t = Config[group]
	local v = t and t[key]
	if v == nil then
		return default
	end
	return v
end

local function ns(points)
	local keys = {}
	for _, p in ipairs(points) do
		table.insert(keys, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(keys)
end

local states = {}

-- ---------------------------------------------------------------- streams

-- Bright streaks racing round the energy trails (client-only trails in the EnergyTrails part).
local function makeStreams(st)
	local part = st.trails
	local origin = part and part:FindFirstChild("Origin")
	local vfx = Config.VFX or {}
	if not origin or vfx.Aura == false or vfx.Trails == false then
		return
	end
	local orbits = Layout.TrailOrbits or {}
	local count = math.max(0, math.floor(opt("VFX", "Streams", 2)))
	for i = 1, math.min(count, 6) do
		local raw = orbits[(i - 1) % math.max(1, #orbits) + 1]
		if raw and #raw > 2 then
			local path = {}
			for _, p in ipairs(raw) do
				table.insert(path, origin.CFrame:PointToWorldSpace(Vector3.new(p[1], p[2], p[3]) * st.scale))
			end
			local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
			a0.Name, a1.Name = "Stream" .. i .. "A", "Stream" .. i .. "B"
			a0.Parent, a1.Parent = part, part
			local trail = Instance.new("Trail")
			trail.Name = "Stream" .. i
			trail.Attachment0, trail.Attachment1 = a0, a1
			trail.Texture = Balloon.Texture("Trail")
			trail.TextureMode = Enum.TextureMode.Stretch
			trail.Lifetime = 0.45
			trail.MinLength = 0.02
			trail.FaceCamera = true
			trail.LightEmission = 1
			trail.LightInfluence = 0
			trail.WidthScale = ns({ { 0, 1 }, { 1, 0.1 } })
			trail.Transparency = ns({ { 0, 0 }, { 1, 1 } })
			trail.Parent = part
			table.insert(st.streams, {
				a0 = a0,
				a1 = a1,
				trail = trail,
				path = path,
				phase = (i - 1) / math.max(1, count),
				dir = i % 2 == 0 and -1 or 1,
			})
		end
	end
end

local function onLoop(path, s)
	local n = #path
	local x = (s % 1) * n
	local k = math.floor(x)
	local a, b = path[k % n + 1], path[(k + 1) % n + 1]
	return a:Lerp(b, x - k)
end

-- ---------------------------------------------------------------- tracking balloons

local function untrack(model)
	local st = states[model]
	if not st then
		return
	end
	states[model] = nil
	for _, s in ipairs(st.streams) do
		s.trail:Destroy()
		s.a0:Destroy()
		s.a1:Destroy()
	end
end

local function track(model)
	if states[model] or not model:IsDescendantOf(Workspace) then
		return
	end
	task.spawn(function()
		local balloon = model:WaitForChild("Balloon", 10)
		local weld = balloon and balloon:WaitForChild("BalloonWeld", 10)
		if not weld or states[model] or not model.Parent then
			return
		end
		local vfx = model:FindFirstChild("VFX")
		local trails = vfx and vfx:FindFirstChild("EnergyTrails")
		local aura = vfx and vfx:FindFirstChild("GoldenAura")
		local st = {
			model = model,
			balloon = balloon,
			weld = weld,
			offset = weld:GetAttribute("Offset") or weld.C0.Position,
			phase = math.random() * 10,
			scale = model:GetAttribute("BalloonScale") or 1,
			hinges = {},
			trails = trails,
			spin = trails and trails:FindFirstChild("TrailSpin"),
			light = aura and aura:FindFirstChildOfClass("PointLight"),
			streams = {},
		}
		for _, name in ipairs({ "LeftWing", "RightWing" }) do
			local wing = model:FindFirstChild(name)
			local hinge = wing and wing:FindFirstChild("WingHinge")
			if hinge and hinge:IsA("Weld") then
				table.insert(st.hinges, { weld = hinge, base = hinge.C0, side = name == "LeftWing" and -1 or 1 })
			end
		end
		if st.spin then
			st.spinBase = st.spin.C0
		end
		if st.light then
			st.lightBase = st.light.Brightness
		end
		makeStreams(st)
		states[model] = st
	end)
end

CollectionService:GetInstanceAddedSignal(Balloon.TAG):Connect(track)
CollectionService:GetInstanceRemovedSignal(Balloon.TAG):Connect(untrack)
for _, model in ipairs(CollectionService:GetTagged(Balloon.TAG)) do
	track(model)
end

-- ---------------------------------------------------------------- animation

local function float(st, dt, t)
	local weld = st.weld
	local root = weld.Part0
	if not (weld.Parent and root and root.Parent) then
		return
	end
	local F = Config.Float or {}
	-- face the way the player faces, but stay upright (only their turn, never their tilt)
	local look = root.CFrame.LookVector
	local flat = Vector3.new(look.X, 0, look.Z)
	if flat.Magnitude > 1e-3 then
		st.facing = flat.Unit
	end
	local facing = CFrame.lookAt(Vector3.zero, st.facing or Vector3.new(0, 0, -1))
	st.rot = st.rot and st.rot:Lerp(facing, 1 - math.exp(-dt * (F.TurnSpeed or 7))) or facing

	-- where it wants to be: beside the player, bobbing and swaying
	local bob = math.sin(t * TAU * (F.BobSpeed or 0.32)) * (F.BobHeight or 0.18)
	local sway = math.sin(t * TAU * (F.SwaySpeed or 0.21)) * (F.Sway or 0.08)
	local target = root.Position + st.rot:VectorToWorldSpace(st.offset + Vector3.new(sway, bob, 0))

	-- follow on a soft spring (snaps if the player teleports). The spring also matches the
	-- player's speed, so it only lags while they speed up, stop or turn, not all the time.
	if not st.pos or (st.pos - target).Magnitude > 25 then
		st.pos, st.vel, st.lastTarget = target, Vector3.zero, target
	end
	local targetVel = (target - (st.lastTarget or target)) / math.max(dt, 1e-3)
	if targetVel.Magnitude > 120 then
		targetVel = Vector3.zero
	end
	st.lastTarget = target
	local k = F.FollowStiffness or 40
	local c = 2 * math.sqrt(k) * (F.FollowDamping or 0.8)
	local steps = math.max(1, math.ceil(dt * 120))
	local h = dt / steps
	for _ = 1, steps do
		st.vel += ((target - st.pos) * k + (targetVel - st.vel) * c) * h
		st.pos += st.vel * h
	end

	-- lean into the motion like a balloon on a string (the top trails behind), plus gentle rocking
	local rel = st.rot:VectorToObjectSpace(st.vel)
	local lean = F.LeanIntoMotion or 0.012
	local maxLean = math.rad(F.MaxLean or 12)
	local tilt = math.rad(F.Tilt or 2.5)
	local pitch = math.clamp(-rel.Z * lean, -maxLean, maxLean) + math.sin(t * 0.83) * tilt * 0.6
	local roll = math.clamp(rel.X * lean, -maxLean, maxLean) + math.sin(t * 0.61 + 1.3) * tilt
	local world = CFrame.new(st.pos) * st.rot * CFrame.Angles(pitch, 0, roll)
	weld.C0 = root.CFrame:ToObjectSpace(world)

	-- the wings rise and fall a little
	local w = t * TAU * (F.WingSpeed or 0.42)
	local flap = math.sin(w) * math.rad(F.WingFlap or 3.5)
	local fold = math.sin(w - 0.8) * math.rad(F.WingFold or 2)
	for _, hinge in ipairs(st.hinges) do
		if hinge.weld.Parent then
			hinge.weld.C0 = hinge.base * CFrame.Angles(0, hinge.side * fold, flap)
		end
	end
end

local function aura(st, now)
	local vfx = Config.VFX or {}
	if st.spin and st.spin.Parent and st.spinBase then
		st.spin.C0 = st.spinBase * CFrame.Angles(0, math.rad(vfx.TrailSpin or 22) * now % TAU, 0)
	end
	local speed = vfx.StreamSpeed or 0.45
	for _, s in ipairs(st.streams) do
		local p = s.dir * now * speed + s.phase
		local w = 0.07 * st.scale
		local pos = onLoop(s.path, p)
		s.a0.Position = pos - Vector3.yAxis * w * 0.5
		s.a1.Position = pos + Vector3.yAxis * w * 0.5
	end
	if st.light and vfx.LightPulse ~= false then
		st.light.Brightness = st.lightBase * (0.85 + 0.15 * math.sin(now * 2.1))
	end
end

-- after its player dies the server lets go of it: drift up and away, then fade
local function release(st, now)
	if not st.released then
		st.released = { start = now, pivot = st.model:GetPivot() }
		for _, s in ipairs(st.streams) do
			s.trail.Enabled = false
		end
		for _, d in ipairs(st.model:GetDescendants()) do
			if d:IsA("ParticleEmitter") then
				d.Rate = d.Rate * 0.4
			end
		end
	end
	local e = now - st.released.start
	local rise = e * 2.4 + e * e * 0.5
	local drift = Vector3.new(math.sin(e * 1.3) * 0.4, rise, 0)
	st.model:PivotTo(st.released.pivot * CFrame.Angles(0, 0, math.sin(e * 1.7) * 0.08) + drift)
	local fade = math.clamp((e - 2.6) / 2, 0, 1)
	for _, d in ipairs(st.model:GetDescendants()) do
		if d:IsA("BasePart") then
			d.LocalTransparencyModifier = fade
		end
	end
end

RunService.RenderStepped:Connect(function(dt)
	dt = math.min(dt, 0.1)
	local now = os.clock()
	local cam = Workspace.CurrentCamera
	local range = opt("Float", "AnimateRange", 150)
	for model, st in pairs(states) do
		if not model.Parent then
			untrack(model)
			continue
		end
		if model:GetAttribute("Released") then
			if opt("Float", "FloatAwayOnDeath", true) then
				release(st, now)
			end
			continue
		end
		local near = cam ~= nil and (cam.CFrame.Position - st.balloon.Position).Magnitude < range
		if near then
			float(st, dt, now + st.phase)
			aura(st, now)
		else
			st.pos, st.lastTarget = nil, nil -- snap back into place when it comes into range again
		end
	end
end)
