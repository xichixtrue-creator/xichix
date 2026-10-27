-- Fortune Staff settings. Lives in ReplicatedStorage.MoneyStaff.Config.
-- Safe to edit: re-running the installer keeps an existing Config.

local Config = {}

Config.Colors = {
	Emerald = Color3.fromRGB(30, 190, 80), -- the money symbol and every emerald (tints their texture)
	Glow = Color3.fromRGB(70, 255, 120), -- the Neon glow inside the emeralds
	Gold = Color3.fromRGB(255, 196, 80), -- only used if the gold texture didn't come in with the import
	Shaft = Color3.fromRGB(14, 22, 18), -- only used if the shaft texture didn't come in with the import
	Light = Color3.fromRGB(90, 255, 130), -- the green light round the head
}

-- How the emeralds look: "Glass" (translucent gem, the default), "Neon" (solid glow)
-- or "Texture" (opaque, with the painted facets).
Config.CrystalStyle = "Glass"
Config.CrystalTransparency = 0.15

Config.Combat = {
	SwingCooldown = 0.45,
	ComboReset = 1.1,
	SwingDamage = { 12, 12, 20 },
	HitDelay = 0.14,
	SwingRange = 8,
	SwingWidth = 9,
	SwingHeight = 7,

	-- the special, Jackpot: a burst of emerald light and gold all the way round you
	SpecialCooldown = 7,
	SpecialWindup = 0.35,
	SpecialDamage = 35,
	SpecialRadius = 12,

	DamageHumanoids = true, -- set false if your game handles damage itself (see StaffHit)
	FriendlyFire = false,
}

-- Keys / buttons for the special (a touch button is added on mobile).
-- Right mouse is left out on purpose: Roblox uses it to turn the camera.
Config.SpecialInputs = { Enum.KeyCode.E, Enum.KeyCode.ButtonY }

-- Optional custom animations ("rbxassetid://123"); empty = Roblox's tool slash / lunge.
Config.Animations = {
	Swing = {},
	Special = "",
}

-- Roll of the crescent slash for each combo step (degrees). 90 = straight down.
Config.SlashAngles = { 70, -65, 95 }

Config.Sounds = {
	Equip = "rbxasset://sounds/unsheath.wav",
	Swing = "rbxasset://sounds/swordslash.wav",
	Special = "rbxasset://sounds/electronicpingshort.wav",
	Impact = "",
}

-- Paste uploaded image IDs here to override the imported textures, e.g. Coin = "rbxassetid://1".
-- Keys: Wisp Glow Sparkle Mote Dollar Coin SlashBand Trail ShockRing GroundCircle
Config.Textures = {}

Config.FallbackTextures = {
	Default = "rbxasset://textures/particles/sparkles_main.dds",
}

Config.VFX = {
	IdleRange = 140, -- the moving parts of the aura only run when the camera is this close
	Aura = true, -- the soft green strands spiralling up the shaft
	AuraSpeed = 0.5, -- how fast the energy flows along them
	SpiralStreams = 2, -- bright streams racing up the spirals now and then
	StreamSpeed = 0.35, -- trips up the spiral per second
	StreamLifetime = 0.4,
	SpinRing = true, -- the gold rings slowly orbit the money symbol
	RingSpeed = 0.7, -- radians per second
	MoneySymbols = true, -- little glowing money symbols drifting round the head
	ScreenFlash = true,
	CameraShake = true,
	SlashRadius = 5.5,
	SlashWidth = 1.3,
	JackpotRadius = 11, -- size of the Jackpot's ring and ground circle
}

return Config
