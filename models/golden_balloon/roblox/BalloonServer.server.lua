-- Golden King Balloon (server). Lives in ServerScriptService.GoldenBalloonServer.
-- Puts the balloon on every player who has it equipped, again after each respawn, and takes
-- it off when they unequip it. See BalloonCosmetic for the API your shop can call.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Folder = ReplicatedStorage:WaitForChild("GoldenKingBalloon")
local Config = require(Folder:WaitForChild("Config"))
local Balloon = require(Folder:WaitForChild("BalloonCosmetic"))

local function wearsIt(player)
	if Balloon.IsEquipped(player) then
		return true
	end
	if Config.AutoEquipEveryone then
		return true
	end
	return Config.AutoEquipInStudio == true and RunService:IsStudio()
end

local function onCharacter(player, character)
	if not wearsIt(player) then
		return
	end
	-- wait until the character has its root and is in the world
	character:WaitForChild("HumanoidRootPart", 10)
	if not character.Parent then
		character.AncestryChanged:Wait()
	end
	if character.Parent and player.Character == character and wearsIt(player) then
		Balloon.Attach(character)
	end
end

local function onPlayer(player)
	player.CharacterAdded:Connect(function(character)
		onCharacter(player, character)
	end)
	if player.Character then
		task.spawn(onCharacter, player, player.Character)
	end
	-- equipping / unequipping while alive
	player:GetAttributeChangedSignal(Config.EquipAttribute):Connect(function()
		local character = player.Character
		if not character then
			return
		end
		local worn = character:FindFirstChild(Balloon.NAME) ~= nil
		if wearsIt(player) and not worn then
			Balloon.Attach(character)
		elseif not wearsIt(player) and worn then
			Balloon.Detach(character)
		end
	end)
end

Players.PlayerAdded:Connect(onPlayer)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(onPlayer, player)
end
